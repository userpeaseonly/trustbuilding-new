import os
import subprocess
import tempfile

import cv2
import numpy as np
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from explorer.models import BuildingExplorer
from explorer.services.cad3d import rebuild_building_3d_geometry
from explorer.services.spatial_matcher import (
    extract_facade_windows_and_canopy,
    extract_red_keymap_crop,
)


class Command(BaseCommand):
    help = 'Rebuild lightweight 3D floor geometry, facade window masks, tree canopy cutouts, and PDF red key-maps.'

    def add_arguments(self, parser):
        parser.add_argument('--building-id', type=int, default=None, help='Optional specific Building PK')

    def handle(self, *args, **options):
        qs = BuildingExplorer.objects.select_related('building').order_by('building_id')
        if options['building_id']:
            qs = qs.filter(building_id=options['building_id'])

        total_floors = 0
        for exp in qs:
            cnt = rebuild_building_3d_geometry(exp)
            total_floors += cnt

            meta = dict(exp.ai_metadata or {})
            # Extract windows + foreground foliage cutout on hero_render cleanly
            if exp.hero_render and default_storage.exists(exp.hero_render.name):
                with default_storage.open(exp.hero_render.name, 'rb') as fh:
                    arr = np.frombuffer(fh.read(), dtype=np.uint8)
                hero_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if hero_bgr is not None:
                    bands = {
                        fe.floor_number: fe.facade_polygon
                        for fe in exp.floors.all()
                        if fe.facade_polygon and len(fe.facade_polygon) >= 3
                    }
                    wc = extract_facade_windows_and_canopy(hero_bgr, bands, rel_prefix=f'b{exp.building_id}_hero')
                    meta['windows_by_floor'] = wc['windows_by_floor']
                    meta['canopy_path'] = wc['canopy_path']

            # Extract red 'Схема блокировки' key-map if source_pdf is present and keymap missing
            if not meta.get('keymap_path') and exp.source_pdf and default_storage.exists(exp.source_pdf.name):
                try:
                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as tmp:
                        with exp.source_pdf.open('rb') as src:
                            for ch in src.chunks():
                                tmp.write(ch)
                        tmp.flush()
                        with tempfile.TemporaryDirectory() as td:
                            out_p = os.path.join(td, 'km_p3')
                            subprocess.check_call(
                                ['pdftoppm', '-r', '140', '-f', '3', '-l', '3', '-singlefile', '-png', tmp.name, out_p],
                                stderr=subprocess.DEVNULL,
                            )
                            if os.path.exists(f'{out_p}.png'):
                                p3_bgr = cv2.imread(f'{out_p}.png')
                                km_bytes = extract_red_keymap_crop(p3_bgr)
                                if km_bytes:
                                    rel_km = f'explorer/keymaps/b{exp.building_id}_keymap.png'
                                    if default_storage.exists(rel_km):
                                        default_storage.delete(rel_km)
                                    meta['keymap_path'] = default_storage.save(rel_km, ContentFile(km_bytes))
                except Exception:
                    pass

            exp.ai_metadata = meta
            exp.save(update_fields=['ai_metadata', 'updated_at'])

            self.stdout.write(
                self.style.SUCCESS(
                    f'Building #{exp.building_id} ({exp.building}): rebuilt {cnt} 3D floor(s), '
                    f'{sum(len(v) for v in (meta.get("windows_by_floor") or {}).values())} windows'
                )
            )

        self.stdout.write(self.style.SUCCESS(f'Done. Total 3D floors rebuilt: {total_floors}'))

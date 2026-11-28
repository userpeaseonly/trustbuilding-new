from pathlib import Path
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from building.models import Building
from explorer.models import BuildingExplorer
from explorer.services.extraction import extract_building_from_pdf


class Command(BaseCommand):
    help = "Import and auto-extract an architectural PDF album into a BuildingExplorer."

    def add_arguments(self, parser):
        parser.add_argument('--building-id', type=int, required=True, help='Target Building PK')
        parser.add_argument('--pdf', type=str, required=True, help='Path to architectural PDF file')
        parser.add_argument('--publish', action='store_true', help='Mark BuildingExplorer as published')
        parser.add_argument('--enable-public-share', action='store_true', help='Enable public share link')

    def handle(self, *args, **options):
        building_id = options['building_id']
        pdf_path = Path(options['pdf'])
        if not pdf_path.is_file():
            raise CommandError(f"PDF file not found: {pdf_path}")

        try:
            building = Building.objects.get(pk=building_id)
        except Building.DoesNotExist as exc:
            raise CommandError(f"Building pk={building_id} does not exist") from exc

        explorer_obj, _ = BuildingExplorer.objects.get_or_create(building=building)
        with pdf_path.open('rb') as fh:
            explorer_obj.source_pdf.save(f'b{building.pk}_album.pdf', File(fh), save=True)

        summary = extract_building_from_pdf(explorer_obj, str(pdf_path))
        if options['publish']:
            explorer_obj.is_published = True
        if options['enable_public_share']:
            explorer_obj.public_share_enabled = True
        explorer_obj.save(update_fields=['is_published', 'public_share_enabled', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(
            f"Building pk={building.pk} ({building.name} Block {building.block_number}): "
            f"matched {summary['matched_apartments']}/{summary['expected_apartments']} apartments "
            f"across {len(summary['floors_extracted'])} floors; hero={explorer_obj.hero_render.name}"
        ))
        for fl, st in sorted(summary.get('per_floor', {}).items(), key=lambda kv: int(kv[0])):
            self.stdout.write(f"  Floor {fl}: regions={st['regions']} matched={st['matched']}/{st['expected']}")

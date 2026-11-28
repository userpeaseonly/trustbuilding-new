import logging
import math
import os
import subprocess
import tempfile

import cv2
import numpy as np
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from explorer.models import BuildingExplorer, ComplexBuildingHotspot
from explorer.services import ai_vision

logger = logging.getLogger(__name__)


def _encode_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode('.png', img)
    if not ok:
        raise ValueError("PNG encoding failed")
    return buf.tobytes()


def slice_multiface_facade(
    faces: list[dict],
    floor_count: int,
    gap_pct: float = 0.03,
) -> dict[int, list[list[float]]]:
    """
    Subdivide 1, 2, or 3 corner-connected perspective facade quadrilaterals into
    continuous corner-wrapping floor bands numbered 1 (bottom) .. `floor_count` (top).

    Each item in `faces`: {'tl': [x,y], 'tr': [x,y], 'br': [x,y], 'bl': [x,y]} in 0..100%.
    """
    if not faces:
        return {}
    floor_count = max(1, int(floor_count))
    bands = {}

    for fl in range(1, floor_count + 1):
        t0 = (fl - 1 + gap_pct) / floor_count
        t1 = (fl - gap_pct) / floor_count

        top_pts = []
        bot_pts = []
        for idx, f in enumerate(faces):
            tl = np.array(f['tl'], dtype=float)
            tr = np.array(f['tr'], dtype=float)
            br = np.array(f['br'], dtype=float)
            bl = np.array(f['bl'], dtype=float)

            p_tl = bl + t1 * (tl - bl)
            p_tr = br + t1 * (tr - br)
            p_bl = bl + t0 * (tl - bl)
            p_br = br + t0 * (tr - br)

            if idx == 0:
                top_pts.append(p_tl)
                bot_pts.append(p_bl)
            top_pts.append(p_tr)
            bot_pts.append(p_br)

        ring = top_pts + list(reversed(bot_pts))
        bands[fl] = [
            [round(float(np.clip(p[0], 0.0, 100.0)), 2), round(float(np.clip(p[1], 0.0, 100.0)), 2)]
            for p in ring
        ]
    return bands


def extract_red_keymap_crop(page_bgr: np.ndarray) -> bytes | None:
    """
    Locate and crop the architectural 'Схема блокировки' block key-map inset
    where the active block is highlighted in bright red inside the site footprint.
    Returns compressed PNG bytes or None if no red key-map inset is present.
    """
    if page_bgr is None or page_bgr.size == 0:
        return None
    h, w = page_bgr.shape[:2]
    b, g, r = page_bgr[..., 0].astype(np.int32), page_bgr[..., 1].astype(np.int32), page_bgr[..., 2].astype(np.int32)

    # Pure red key-map highlight usually sits in bottom-right / bottom half inset
    red_mask = ((r > 185) & (g < 75) & (b < 75)).astype(np.uint8)
    # Ignore title red header line at very top 12%
    red_mask[: int(h * 0.15), :] = 0
    if int(red_mask.sum()) < 60:
        return None

    # Prefer red cluster in bottom-right quadrant where CIS/Uzbek title-block key-maps live
    br_mask = red_mask.copy()
    if br_mask[int(h * 0.55):, int(w * 0.50):].sum() >= 60:
        br_mask[: int(h * 0.55), :] = 0
        br_mask[:, : int(w * 0.50)] = 0

    n, _lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(br_mask, np.ones((7, 7), np.uint8)), 8)
    if n <= 1:
        return None
    best = max(range(1, n), key=lambda i: int(st[i, cv2.CC_STAT_AREA]))
    if int(st[best, cv2.CC_STAT_AREA]) < 50:
        return None

    rx, ry = int(st[best, cv2.CC_STAT_LEFT]), int(st[best, cv2.CC_STAT_TOP])
    rw, rh = int(st[best, cv2.CC_STAT_WIDTH]), int(st[best, cv2.CC_STAT_HEIGHT])
    rcx, rcy = rx + rw // 2, ry + rh // 2

    # Snap outward to enclosing black rectangular border around key-map or use generous symmetric frame
    gray = cv2.cvtColor(page_bgr, cv2.COLOR_BGR2GRAY)
    box_w = max(int(w * 0.14), rw * 4)
    box_h = max(int(h * 0.16), rh * 4)
    x1 = max(0, rcx - box_w // 2)
    y1 = max(0, rcy - box_h // 2)
    x2 = min(w, x1 + box_w)
    y2 = min(h, y1 + box_h)

    crop = page_bgr[y1:y2, x1:x2]
    # Trim clean surrounding whitespace if inset frame lines exist
    sub_g = gray[y1:y2, x1:x2]
    dark = (sub_g < 190).astype(np.uint8)
    if dark.any():
        ys, xs = np.nonzero(dark)
        x1_i, x2_i = max(0, int(xs.min()) - 8), min(crop.shape[1], int(xs.max()) + 8)
        y1_i, y2_i = max(0, int(ys.min()) - 8), min(crop.shape[0], int(ys.max()) + 8)
        if (x2_i - x1_i) >= 40 and (y2_i - y1_i) >= 40:
            crop = crop[y1_i:y2_i, x1_i:x2_i]

    ch, cw = crop.shape[:2]
    if max(ch, cw) > 480:
        s = 480.0 / max(ch, cw)
        crop = cv2.resize(crop, (int(cw * s), int(ch * s)), interpolation=cv2.INTER_AREA)
    return _encode_png(crop)


def extract_facade_windows_and_canopy(
    render_bgr: np.ndarray,
    floor_polygons: dict[int, list[list[float]]],
    rel_prefix: str,
) -> dict:
    """
    Detect actual dark architectural glass window panes inside each floor's facade polygon
    (for realistic warm interior lighting in Night/Sunset mode) AND foreground green tree foliage
    (saved as a transparent RGBA overlay so foliage cleanly occludes floor highlights).
    """
    if render_bgr is None or render_bgr.size == 0:
        return {'windows_by_floor': {}, 'canopy_path': ''}

    h, w = render_bgr.shape[:2]
    hsv = cv2.cvtColor(render_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(render_bgr, cv2.COLOR_BGR2GRAY)
    b, g, r = render_bgr[..., 0].astype(np.int32), render_bgr[..., 1].astype(np.int32), render_bgr[..., 2].astype(np.int32)

    # 1. Foreground green/olive foliage mask (trees/bushes standing in front of Floor 1..2)
    green_mask = (
        (g >= r + 1)
        & (g > b + 8)
        & (hsv[..., 0] >= 22)
        & (hsv[..., 0] <= 90)
        & (hsv[..., 1] > 24)
        & (hsv[..., 2] > 24)
    ).astype(np.uint8)
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    # Restrict canopy cutout overlay strictly to pixels overlapping building facade bounds
    facade_union = np.zeros((h, w), dtype=np.uint8)
    for poly in floor_polygons.values():
        if poly and len(poly) >= 3:
            pts = np.array([[int(p[0] / 100.0 * w), int(p[1] / 100.0 * h)] for p in poly], dtype=np.int32)
            cv2.fillPoly(facade_union, [pts], 1)

    canopy_fg = green_mask & facade_union
    canopy_path = ''
    # Save RGBA cutout when trees actually overlap >= 0.4% of facade pixels
    if facade_union.any() and (int(canopy_fg.sum()) / max(1, int(facade_union.sum()))) >= 0.004:
        feathered = cv2.GaussianBlur((canopy_fg * 255).astype(np.uint8), (5, 5), 0)
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[..., :3] = render_bgr
        rgba[..., 3] = feathered
        rel_c = f'explorer/renders/{rel_prefix}_canopy.png'
        if default_storage.exists(rel_c):
            default_storage.delete(rel_c)
        canopy_path = default_storage.save(rel_c, ContentFile(_encode_png(rgba)))

    # 2. Dark glass glazing rectangles inside each floor band (exclude green trees)
    dark_glass = ((gray < 102) & (hsv[..., 1] < 95) & (~(green_mask > 0))).astype(np.uint8)
    # Clean hairline balcony rails inside windows so window pane forms coherent glow box
    dark_glass = cv2.morphologyEx(dark_glass, cv2.MORPH_CLOSE, np.ones((5, 3), np.uint8))
    dark_glass = cv2.morphologyEx(dark_glass, cv2.MORPH_OPEN, np.ones((4, 3), np.uint8))

    windows_by_floor: dict[str, list[list[float]]] = {}
    max_win_w = max(10, int(w * 0.055))
    min_win_area = max(35, int((w * h) * 0.000025))

    for fl_num, poly in sorted(floor_polygons.items()):
        if not poly or len(poly) < 3:
            continue
        fl_mask = np.zeros((h, w), dtype=np.uint8)
        pts = np.array([[int(p[0] / 100.0 * w), int(p[1] / 100.0 * h)] for p in poly], dtype=np.int32)
        cv2.fillPoly(fl_mask, [pts], 1)
        # Shrink inward slightly from slab trim so dark horizontal cornices aren't treated as windows
        erode_y = max(3, int((pts[:, 1].max() - pts[:, 1].min()) * 0.14))
        fl_inner = cv2.erode(fl_mask, np.ones((erode_y, 3), np.uint8))
        fl_win = dark_glass & (fl_inner if fl_inner.any() else fl_mask)

        n, _lab, st, _ = cv2.connectedComponentsWithStats(fl_win, 8)
        rects = []
        for idx in range(1, n):
            area = int(st[idx, cv2.CC_STAT_AREA])
            bw = int(st[idx, cv2.CC_STAT_WIDTH])
            bh = int(st[idx, cv2.CC_STAT_HEIGHT])
            if area < min_win_area or bh < 6 or bw < 4 or bw > max_win_w * 2:
                continue
            # Filter out overly wide horizontal shadow bands
            if bw > bh * 3.8:
                continue
            bx = int(st[idx, cv2.CC_STAT_LEFT])
            by = int(st[idx, cv2.CC_STAT_TOP])
            rects.append([
                round(bx / w * 100.0, 2),
                round(by / h * 100.0, 2),
                round(bw / w * 100.0, 2),
                round(bh / h * 100.0, 2),
            ])
        if rects:
            windows_by_floor[str(fl_num)] = rects[:120]

    return {
        'windows_by_floor': windows_by_floor,
        'canopy_path': canopy_path,
    }


def _collect_complex_ai_inputs(complex_obj) -> tuple[bytes | None, bytes | None, list[tuple[int, str, bytes]], list[dict]]:
    """
    Gather aerial masterplan render, site Genplan page (supporting BOTH Complex-first masterplan_pdf
    AND Building-first linked BuildingExplorers), and any extracted red key-maps.
    """
    aerial_bytes = None
    if complex_obj.masterplan_image and default_storage.exists(complex_obj.masterplan_image.name):
        with default_storage.open(complex_obj.masterplan_image.name, 'rb') as fh:
            aerial_bytes = fh.read()

    genplan_bytes = None
    # Workflow B (Complex-First): read uploaded masterplan_pdf if provided
    if complex_obj.masterplan_pdf and default_storage.exists(complex_obj.masterplan_pdf.name):
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as tmp:
                with complex_obj.masterplan_pdf.open('rb') as src:
                    for ch in src.chunks():
                        tmp.write(ch)
                tmp.flush()
                with tempfile.TemporaryDirectory() as td:
                    out_p = os.path.join(td, 'cx_mp')
                    subprocess.check_call(
                        ['pdftoppm', '-r', '110', '-f', '1', '-l', '1', '-singlefile', '-png', tmp.name, out_p],
                        stderr=subprocess.DEVNULL,
                    )
                    if os.path.exists(f'{out_p}.png'):
                        with open(f'{out_p}.png', 'rb') as f:
                            genplan_bytes = f.read()
        except Exception as exc:
            logger.warning("Failed to render complex masterplan_pdf: %s", exc)

    buildings = list(complex_obj.company.buildings.all().order_by('block_number', 'id'))
    explorers_by_bid = {
        e.building_id: e
        for e in BuildingExplorer.objects.filter(building__in=buildings)
    }

    keymap_images = []
    buildings_meta = []
    for b in buildings:
        exp = explorers_by_bid.get(b.pk)
        b_label = f"{b.name} (Block {b.block_number})" if b.block_number else b.name
        buildings_meta.append({
            'id': b.pk,
            'name': b.name,
            'block_number': b.block_number or '',
            'floor_count': b.floor_count,
            'apartments_per_floor': b.apartments_per_floor,
        })
        if exp:
            km_rel = (exp.ai_metadata or {}).get('keymap_path', '')
            if km_rel and default_storage.exists(km_rel):
                with default_storage.open(km_rel, 'rb') as fh:
                    keymap_images.append((b.pk, b_label, fh.read()))
            if not genplan_bytes:
                mp_rel = (exp.ai_metadata or {}).get('masterplan_path', '')
                if not mp_rel:
                    for er in (exp.extra_renders or []):
                        if 'masterplan' in (er.get('label') or '').lower() or er.get('sky_score', 0) < 0:
                            mp_rel = er.get('path', '')
                            break
                if mp_rel and default_storage.exists(mp_rel):
                    with default_storage.open(mp_rel, 'rb') as fh:
                        genplan_bytes = fh.read()

    return aerial_bytes, genplan_bytes, keymap_images, buildings_meta


def auto_detect_complex_blocks(complex_obj) -> dict:
    """
    Automatically match target buildings in `complex_obj.company` onto `complex_obj.masterplan_image`
    using Gemini multi-image cross-registration (with Genplan + Red Key-Maps + Compass sync).
    """
    aerial_bytes, genplan_bytes, keymap_images, buildings_meta = _collect_complex_ai_inputs(complex_obj)
    if not aerial_bytes:
        return {'ok': False, 'error': 'Masterplan/aerial image is required before AI block detection.'}
    if not buildings_meta:
        return {'ok': False, 'error': 'No buildings exist yet for this company.'}

    status = ai_vision.get_ai_provider_status()
    if not status['gemini_ready'] and not status['deepseek_ready']:
        return {
            'ok': False,
            'needs_key': True,
            'error': 'Configure GEMINI_API_KEY (or AI_ENABLED DeepSeek) to run AI block matching.',
        }

    matched = ai_vision.match_complex_blocks_with_ai(
        aerial_bytes,
        buildings_meta,
        genplan_bytes=genplan_bytes,
        keymap_images=keymap_images,
    )
    if not matched:
        return {'ok': False, 'error': 'AI vision could not resolve building blocks on this image.'}

    # Optionally update compass azimuth from Genplan when available
    compass_updated = None
    if genplan_bytes:
        ang = ai_vision.extract_compass_with_ai(genplan_bytes)
        if ang is not None:
            complex_obj.compass_angle = ang
            complex_obj.save(update_fields=['compass_angle', 'updated_at'])
            BuildingExplorer.objects.filter(building__company=complex_obj.company).update(compass_angle=ang)
            compass_updated = ang

    valid_buildings = {b.pk: b for b in complex_obj.company.buildings.all()}
    saved = 0
    complex_obj.building_hotspots.all().delete()
    to_create = []
    for item in matched:
        b_obj = valid_buildings.get(item['building_id'])
        if not b_obj:
            continue
        to_create.append(
            ComplexBuildingHotspot(
                complex_explorer=complex_obj,
                building=b_obj,
                polygon_points=item['polygon_points'],
                label_x=item['label_x'],
                label_y=item['label_y'],
                ai_confidence=item['confidence'],
                ai_notes=item['notes'][:255],
            )
        )
        BuildingExplorer.objects.filter(building=b_obj).update(complex_explorer=complex_obj)
        saved += 1

    ComplexBuildingHotspot.objects.bulk_create(to_create)
    complex_obj.ai_metadata = {
        **(complex_obj.ai_metadata or {}),
        'last_match_provider': 'gemini' if status['gemini_ready'] else 'deepseek',
        'matched_count': saved,
        'had_genplan': bool(genplan_bytes),
        'keymap_count': len(keymap_images),
    }
    complex_obj.save(update_fields=['ai_metadata', 'updated_at'])

    return {
        'ok': True,
        'saved': saved,
        'compass_angle': compass_updated,
        'hotspots': [
            {
                'building_id': hs.building_id,
                'polygon_points': hs.polygon_points,
                'label_x': hs.label_x,
                'label_y': hs.label_y,
                'ai_confidence': hs.ai_confidence,
                'ai_notes': hs.ai_notes,
            }
            for hs in to_create
        ],
    }


def _collect_building_facade_context(building_explorer: BuildingExplorer) -> tuple[str, bytes | None, bytes | None, list[dict]]:
    """Gather building label, red key-map thumbnail, Genplan masterplan image, and sibling block metadata."""
    b = building_explorer.building
    b_label = f"{b.name} (Block {b.block_number})" if b.block_number else b.name
    meta = building_explorer.ai_metadata or {}

    keymap_bytes = None
    km_rel = meta.get('keymap_path') or f'explorer/keymaps/b{b.pk}_keymap.png'
    if km_rel and default_storage.exists(km_rel):
        with default_storage.open(km_rel, 'rb') as fh:
            keymap_bytes = fh.read()

    genplan_bytes = None
    mp_rel = meta.get('masterplan_path', '')
    if not mp_rel:
        for er in (building_explorer.extra_renders or []):
            if 'masterplan' in (er.get('label') or '').lower() or er.get('sky_score', 0) < 0:
                mp_rel = er.get('path', '')
                break
    if mp_rel and default_storage.exists(mp_rel):
        with default_storage.open(mp_rel, 'rb') as fh:
            genplan_bytes = fh.read()
    elif building_explorer.complex_explorer and building_explorer.complex_explorer.masterplan_pdf:
        cx_pdf = building_explorer.complex_explorer.masterplan_pdf
        if default_storage.exists(cx_pdf.name):
            try:
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as tmp:
                    with cx_pdf.open('rb') as src:
                        for ch in src.chunks():
                            tmp.write(ch)
                    tmp.flush()
                    with tempfile.TemporaryDirectory() as td:
                        out_p = os.path.join(td, 'mp')
                        subprocess.check_call(
                            ['pdftoppm', '-r', '110', '-f', '1', '-l', '1', '-singlefile', '-png', tmp.name, out_p],
                            stderr=subprocess.DEVNULL,
                        )
                        if os.path.exists(f'{out_p}.png'):
                            with open(f'{out_p}.png', 'rb') as f:
                                genplan_bytes = f.read()
            except Exception as exc:
                logger.warning("Could not read complex masterplan_pdf context: %s", exc)

    siblings = []
    for sb in b.company.buildings.all().order_by('block_number', 'id'):
        siblings.append({
            'id': sb.pk,
            'name': sb.name,
            'block_number': sb.block_number or '',
            'floor_count': sb.floor_count,
        })
    return b_label, keymap_bytes, genplan_bytes, siblings


def generate_building_atmosphere_renders(
    building_explorer: BuildingExplorer,
    *,
    modes: tuple[str, ...] = ('sunset', 'night'),
    save_model: bool = True,
) -> dict:
    """
    Use Gemini native image editing to generate photorealistic geometry-locked Sunset and Night renders
    from `building_explorer.hero_render` and persist paths in `ai_metadata`.
    """
    if not building_explorer.hero_render or not default_storage.exists(building_explorer.hero_render.name):
        return {'ok': False, 'error': 'Upload or extract a Hero exterior render first.'}

    if not ai_vision.get_ai_provider_status().get('gemini_ready'):
        return {'ok': False, 'needs_key': True, 'error': 'GEMINI_API_KEY is required to generate AI Sunset & Night renders.'}

    with default_storage.open(building_explorer.hero_render.name, 'rb') as fh:
        hero_bytes = fh.read()

    meta = dict(building_explorer.ai_metadata or {})
    generated = {}
    for mode in modes:
        if mode not in ('sunset', 'night'):
            continue
        out_bytes = ai_vision.generate_atmosphere_render_with_ai(hero_bytes, mode)
        if not out_bytes:
            continue
        rel = f'explorer/renders/b{building_explorer.building_id}_hero_{mode}.jpg'
        if default_storage.exists(rel):
            default_storage.delete(rel)
        saved_rel = default_storage.save(rel, ContentFile(out_bytes))
        meta[f'{mode}_hero_path'] = saved_rel
        generated[mode] = saved_rel

    if not generated:
        return {'ok': False, 'error': 'AI could not generate atmosphere renders right now. Please try again.'}

    building_explorer.ai_metadata = meta
    if save_model:
        building_explorer.save(update_fields=['ai_metadata', 'updated_at'])

    return {
        'ok': True,
        'generated': list(generated.keys()),
        'sunset_url': default_storage.url(meta['sunset_hero_path']) if meta.get('sunset_hero_path') and default_storage.exists(meta['sunset_hero_path']) else '',
        'night_url': default_storage.url(meta['night_hero_path']) if meta.get('night_hero_path') and default_storage.exists(meta['night_hero_path']) else '',
    }


def analyze_view_overlay(building_explorer: BuildingExplorer, view_path: str) -> dict:
    """
    Detect the target block's floor bands on one extra camera angle (`view_path` from `extra_renders`)
    and store them under `view_overlays[view_path]`. The hero render is never touched.
    """
    valid = {er.get('path') for er in (building_explorer.extra_renders or []) if er.get('sky_score', 0) >= 0}
    if view_path not in valid or not default_storage.exists(view_path):
        return {'ok': False, 'error': 'Unknown or missing view image.'}

    with default_storage.open(view_path, 'rb') as fh:
        raw_bytes = fh.read()

    b_label, keymap_bytes, genplan_bytes, siblings = _collect_building_facade_context(building_explorer)
    floor_count = building_explorer.building.floor_count
    faces_res = ai_vision.detect_facade_and_faces_with_ai(
        raw_bytes,
        floor_count,
        building_label=b_label,
        keymap_bytes=keymap_bytes,
        genplan_bytes=genplan_bytes,
        complex_buildings=siblings,
    )
    if not faces_res or not faces_res.get('faces'):
        return {'ok': False, 'error': 'AI could not locate this block on the selected view. Outline the floors manually.'}

    bands = slice_multiface_facade(faces_res['faces'], floor_count)
    overlays = dict(building_explorer.view_overlays or {})
    overlays[view_path] = {
        'floors': {str(k): v for k, v in bands.items()},
        'faces': faces_res['faces'],
        'source': 'ai',
    }
    building_explorer.view_overlays = overlays
    building_explorer.save(update_fields=['view_overlays', 'updated_at'])
    return {
        'ok': True,
        'faces_detected': len(faces_res['faces']),
        'floors': overlays[view_path]['floors'],
        'facade_faces': faces_res['faces'],
    }


def auto_analyze_building_facade(
    building_explorer: BuildingExplorer,
    *,
    reselect_hero: bool = False,
    generate_atmosphere: bool = False,
) -> dict:
    """
    Analyze `building_explorer.hero_render` using Key-Map & Genplan-guided Gemini Pro/Flash spatial grounding
    (for target-block isolation & multi-face floor bands) + OpenCV window & green tree canopy extraction.
    Optionally re-selects the best hero render across `building_explorer.extra_renders` first when `reselect_hero=True`.
    """
    b_label, keymap_bytes, genplan_bytes, siblings = _collect_building_facade_context(building_explorer)
    extra = list(building_explorer.extra_renders or [])

    if reselect_hero and extra:
        candidates = []
        for idx, er in enumerate(extra):
            if er.get('sky_score', 0) < 0:
                continue
            p = er.get('path', '')
            if p and default_storage.exists(p):
                with default_storage.open(p, 'rb') as fh:
                    candidates.append((idx, p, fh.read()))
        if len(candidates) >= 2:
            pick = ai_vision.select_best_hero_render_with_ai(
                [(idx, bdata) for idx, _p, bdata in candidates],
                block_label=b_label,
                keymap_bytes=keymap_bytes,
                genplan_bytes=genplan_bytes,
            )
            if pick:
                chosen = next((c for c in candidates if c[0] == pick['best_index']), None)
                if chosen:
                    chosen_bgr = cv2.imdecode(np.frombuffer(chosen[2], dtype=np.uint8), cv2.IMREAD_COLOR)
                    if chosen_bgr is not None:
                        ch_h, ch_w = chosen_bgr.shape[:2]
                        rel_hero = f'explorer/renders/b{building_explorer.building_id}_hero.png'
                        if building_explorer.hero_render and default_storage.exists(building_explorer.hero_render.name):
                            default_storage.delete(building_explorer.hero_render.name)
                        ok_e, buf_e = cv2.imencode('.png', chosen_bgr)
                        if ok_e:
                            building_explorer.hero_render.save(os.path.basename(rel_hero), ContentFile(buf_e.tobytes()), save=False)
                            building_explorer.hero_width = int(ch_w)
                            building_explorer.hero_height = int(ch_h)

    if not building_explorer.hero_render or not default_storage.exists(building_explorer.hero_render.name):
        return {'ok': False, 'error': 'Upload or extract an exterior render first.'}

    with default_storage.open(building_explorer.hero_render.name, 'rb') as fh:
        raw_bytes = fh.read()
    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    render_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if render_bgr is None:
        return {'ok': False, 'error': 'Unable to decode hero render.'}

    floor_count = building_explorer.building.floor_count
    faces_res = ai_vision.detect_facade_and_faces_with_ai(
        raw_bytes,
        floor_count,
        building_label=b_label,
        keymap_bytes=keymap_bytes,
        genplan_bytes=genplan_bytes,
        complex_buildings=siblings,
    )
    floors_qs = list(building_explorer.floors.order_by('floor_number'))

    bands: dict[int, list[list[float]]] = {}
    if faces_res and faces_res.get('faces'):
        building_explorer.facade_faces = faces_res['faces']
        bands = slice_multiface_facade(faces_res['faces'], floor_count)
        for fe in floors_qs:
            if fe.floor_number in bands:
                fe.facade_polygon = bands[fe.floor_number]
                fe.save(update_fields=['facade_polygon'])
    else:
        bands = {fe.floor_number: fe.facade_polygon for fe in floors_qs if fe.facade_polygon}

    win_canopy = extract_facade_windows_and_canopy(
        render_bgr,
        bands,
        rel_prefix=f'b{building_explorer.building_id}_hero',
    )
    meta = dict(building_explorer.ai_metadata or {})
    meta['windows_by_floor'] = win_canopy['windows_by_floor']
    meta['canopy_path'] = win_canopy['canopy_path']
    if faces_res:
        meta['camera_view'] = faces_res.get('camera_view', '')
        meta['facade_notes'] = faces_res.get('notes', '')
    building_explorer.ai_metadata = meta
    building_explorer.save(update_fields=['hero_render', 'hero_width', 'hero_height', 'facade_faces', 'ai_metadata', 'updated_at'])

    atmo_res = None
    if generate_atmosphere and building_explorer.atmosphere_enabled:
        atmo_res = generate_building_atmosphere_renders(building_explorer, save_model=True)

    return {
        'ok': True,
        'faces_detected': len(building_explorer.facade_faces or []),
        'camera_view': meta.get('camera_view', ''),
        'facade_notes': meta.get('facade_notes', ''),
        'window_floors': len(win_canopy['windows_by_floor']),
        'total_windows': sum(len(v) for v in win_canopy['windows_by_floor'].values()),
        'has_canopy': bool(win_canopy['canopy_path']),
        'atmosphere_generated': atmo_res.get('generated', []) if atmo_res else [],
    }

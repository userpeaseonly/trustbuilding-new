import math
import cv2
import numpy as np
from django.core.files.storage import default_storage
from django.utils.translation import gettext as _


def _shoelace_area(pts: list[list[float]]) -> float:
    if not pts or len(pts) < 3:
        return 0.0
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def compute_plan_real_scale(
    plan_w: int,
    plan_h: int,
    regions: list[dict],
) -> tuple[float, float]:
    """
    Estimate real architectural physical width and depth (in meters) for the 100%x100%
    plan coordinate box using matched apartment areas when available, with aspect fallback.
    """
    aspect = max(0.3, float(plan_w) / max(1, plan_h))
    matched_pct_area = 0.0
    matched_m2 = 0.0

    for reg in regions:
        area_m2 = float(reg.get('total_area') or 0.0)
        poly = reg.get('polygon_points') or []
        pct_area = _shoelace_area(poly)
        if area_m2 > 5.0 and pct_area > 5.0:
            matched_m2 += area_m2
            matched_pct_area += pct_area

    if matched_m2 > 0.0 and matched_pct_area > 0.0:
        # 1% in X is k*aspect, 1% in Y is k -> (k^2 * aspect) * pct_area == matched_m2
        k = math.sqrt(matched_m2 / (matched_pct_area * aspect))
        # Normalize against typical CAD gross-to-net wall & stairwell allowance (~1.12x linear)
        scene_w = round(max(16.0, min(95.0, 100.0 * k * aspect)), 2)
        scene_d = round(scene_w / aspect, 2)
        return scene_w, scene_d

    scene_w = 38.0 if aspect >= 1.2 else 28.0
    scene_d = round(scene_w / aspect, 2)
    return scene_w, scene_d


def _rle_axis_boxes(
    bin_mask: np.ndarray,
    full_w: int,
    full_h: int,
    *,
    transpose: bool,
    min_run: int,
    max_thick_px: int,
    min_area: int,
) -> list[list[float]]:
    m = bin_mask.T if transpose else bin_mask
    mh, _mw = m.shape[:2]
    active: dict[tuple[int, int], list[int]] = {}
    finished: list[tuple[int, int, int, int]] = []

    for y in range(mh):
        row = m[y]
        padded = np.concatenate(([0], row, [0]))
        diffs = np.diff(padded.astype(np.int8))
        starts = np.where(diffs == 1)[0]
        ends = np.where(diffs == -1)[0]

        curr = [(int(s), int(e)) for s, e in zip(starts, ends) if (e - s) >= min_run]
        next_active: dict[tuple[int, int], list[int]] = {}
        used = set()

        for s, e in curr:
            best_k = None
            for k in active:
                if k in used:
                    continue
                if abs(k[0] - s) <= 2 and abs(k[1] - e) <= 2:
                    best_k = k
                    break
            if best_k is not None:
                used.add(best_k)
                span = active[best_k]
                next_active[best_k] = [span[0], y]
            else:
                next_active[(s, e)] = [y, y]

        for k, span in active.items():
            if k not in used:
                finished.append((k[0], span[0], k[1] - k[0], span[1] - span[0] + 1))
        active = next_active

    for k, span in active.items():
        finished.append((k[0], span[0], k[1] - k[0], span[1] - span[0] + 1))

    boxes = []
    for x, y, rw, rh in finished:
        if transpose:
            x, y, rw, rh = y, x, rh, rw
        if rw * rh < min_area or (rw > max_thick_px and rh > max_thick_px):
            continue
        boxes.append([
            round((x + rw / 2.0) / full_w * 100.0, 2),
            round((y + rh / 2.0) / full_h * 100.0, 2),
            round(rw / full_w * 100.0, 2),
            round(rh / full_h * 100.0, 2),
        ])
    return boxes


def _mask_to_clean_boxes(
    mask: np.ndarray,
    *,
    min_len: int = 8,
    min_run: int = 3,
    min_area: int = 18,
    max_thick_ratio: float = 0.055,
) -> list[list[float]]:
    """Decompose a binary CAD mask cleanly into [cx, cy, w, h] percentage boxes."""
    h, w = mask.shape[:2]
    max_t = max(14, int(min(h, w) * max_thick_ratio))

    kh = cv2.getStructuringElement(cv2.MORPH_RECT, (min_len, 1))
    kv = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_len))
    h_mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kh)
    v_mask = cv2.morphologyEx(mask & (~h_mask), cv2.MORPH_OPEN, kv)
    rem = cv2.morphologyEx(mask & (~h_mask) & (~v_mask), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    boxes = _rle_axis_boxes(
        h_mask, w, h, transpose=False, min_run=min_run, max_thick_px=max_t, min_area=min_area
    ) + _rle_axis_boxes(
        v_mask, w, h, transpose=True, min_run=min_run, max_thick_px=max_t, min_area=min_area
    )

    n, _lab, st, _ = cv2.connectedComponentsWithStats(rem, 8)
    for idx in range(1, n):
        area = int(st[idx, cv2.CC_STAT_AREA])
        if area < max(min_area, 20):
            continue
        bx, by = int(st[idx, cv2.CC_STAT_LEFT]), int(st[idx, cv2.CC_STAT_TOP])
        bw, bh = int(st[idx, cv2.CC_STAT_WIDTH]), int(st[idx, cv2.CC_STAT_HEIGHT])
        if bw > max_t and bh > max_t:
            continue
        boxes.append([
            round((bx + bw / 2.0) / w * 100.0, 2),
            round((by + bh / 2.0) / h * 100.0, 2),
            round(bw / w * 100.0, 2),
            round(bh / h * 100.0, 2),
        ])
    return boxes


def _direction_label_from_vector(dx: float, dy: float, compass_angle_deg: float) -> dict[str, str]:
    """
    Convert outward plan normal vector (dx, dy in screen coords: +y down) into true solar exposure
    given `compass_angle_deg` (degrees clockwise of screen-up for true North).
    """
    # Screen vector angle clockwise from UP (0, -1)
    screen_cw = math.degrees(math.atan2(dx, -dy)) % 360.0
    bearing = (screen_cw - compass_angle_deg) % 360.0
    dirs = [
        ('N', _('North • Cool Even Light')),
        ('NE', _('North-East • Gentle Morning Sun')),
        ('E', _('East • Morning Sun')),
        ('SE', _('South-East • Bright Morning & Midday Sun')),
        ('S', _('South • All-Day Sun')),
        ('SW', _('South-West • Warm Afternoon Sun')),
        ('W', _('West • Sunset & Evening Light')),
        ('NW', _('North-West • Late Evening Light')),
    ]
    idx = int((bearing + 22.5) // 45) % 8
    cardinal, tag = dirs[idx]
    return {'cardinal': cardinal, 'sun_tag': str(tag)}


def extract_floor_3d_geometry(
    plan_bgr: np.ndarray,
    regions: list[dict],
    *,
    floor_number: int = 1,
    compass_angle: float = 0.0,
) -> dict:
    """
    Extract lightweight WebGL-ready 3D wall prisms, glass window strips, slab footprint,
    and per-apartment solar window orientation from a cropped architectural floor plan.

    Works universally across vector-rendered PDFs AND uploaded raster floor plan images.
    """
    h, w = plan_bgr.shape[:2]

    slab = np.zeros((h, w), dtype=np.uint8)
    for reg in regions:
        pts = reg.get('polygon_points') or []
        if len(pts) >= 3:
            arr = np.array([[int(p[0] / 100.0 * w), int(p[1] / 100.0 * h)] for p in pts], dtype=np.int32)
            cv2.fillPoly(slab, [arr], 1)

    if slab.any():
        pad_px = max(18, int(min(h, w) * 0.028))
        slab_pad = cv2.dilate(slab, np.ones((pad_px, pad_px), np.uint8))
        # Seal small central elevator/corridor holes for slab plate polygon
        slab_closed = cv2.morphologyEx(slab_pad, cv2.MORPH_CLOSE, np.ones((pad_px * 2 + 1, pad_px * 2 + 1), np.uint8))
        cnts, _ = cv2.findContours(slab_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        slab_polygons = []
        for cnt in sorted(cnts, key=cv2.contourArea, reverse=True)[:4]:
            area = cv2.contourArea(cnt)
            if area < 0.015 * h * w:
                continue
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.004 * peri, True)
            pts = [
                [round(float(pt[0][0]) / w * 100.0, 2), round(float(pt[0][1]) / h * 100.0, 2)]
                for pt in approx
            ]
            if len(pts) >= 3:
                slab_polygons.append(pts)
    else:
        slab_pad = np.ones((h, w), dtype=np.uint8)
        slab_polygons = [[[4.0, 4.0], [96.0, 4.0], [96.0, 96.0], [4.0, 96.0]]]

    # Identify exterior perimeter shell to tag load-bearing/exterior walls vs interior partitions
    ext_zone = np.zeros((h, w), dtype=np.uint8)
    if slab.any():
        ring_pad = max(14, int(min(h, w) * 0.018))
        slab_core_eroded = cv2.erode(cv2.morphologyEx(slab, cv2.MORPH_CLOSE, np.ones((ring_pad, ring_pad), np.uint8)), np.ones((8, 8), np.uint8))
        ext_zone = (slab_pad > 0) & (slab_core_eroded == 0)

    gray = cv2.cvtColor(plan_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(plan_bgr, cv2.COLOR_BGR2HSV)
    b, g, r = plan_bgr[..., 0].astype(np.int32), plan_bgr[..., 1].astype(np.int32), plan_bgr[..., 2].astype(np.int32)

    # 1. Distinguish pure glass windows (deep vivid blue) vs interior cyan party-wall fills vs pastel rooms
    is_pure_blue = (b - np.maximum(r, g) > 85) & (b > 135) & (slab_pad > 0)
    is_cyan_fill = (hsv[..., 0] >= 86) & (hsv[..., 0] <= 128) & (hsv[..., 1] > 110) & (hsv[..., 2] > 140) & (b - r > 65) & (slab_pad > 0)
    is_any_blue = is_pure_blue | is_cyan_fill

    # True glass windows live only along exterior/facade glazing strips and stay thin (not blocky area labels)
    w_cand = (is_pure_blue | (is_cyan_fill & (ext_zone > 0 if ext_zone.any() else True))).astype(np.uint8)
    wh = cv2.morphologyEx(cv2.morphologyEx(w_cand, cv2.MORPH_CLOSE, np.ones((3, 9), np.uint8)), cv2.MORPH_OPEN, np.ones((1, 10), np.uint8))
    wv = cv2.morphologyEx(cv2.morphologyEx(w_cand, cv2.MORPH_CLOSE, np.ones((9, 3), np.uint8)) & (~wh), cv2.MORPH_OPEN, np.ones((10, 1), np.uint8))

    max_w_thick = max(14, int(min(h, w) * 0.018))
    clean_win = np.zeros((h, w), dtype=np.uint8)
    for m_dir, is_h in [(wh, True), (wv, False)]:
        n_c, lab_c, st_c, _ = cv2.connectedComponentsWithStats(m_dir, 8)
        for ci in range(1, n_c):
            bw = int(st_c[ci, cv2.CC_STAT_WIDTH])
            bh = int(st_c[ci, cv2.CC_STAT_HEIGHT])
            area = int(st_c[ci, cv2.CC_STAT_AREA])
            if area < 24:
                continue
            thick = bh if is_h else bw
            span = bw if is_h else bh
            if thick <= max_w_thick and span >= thick * 1.35:
                clean_win[lab_c == ci] = 1

    # 2. Seal double-line CAD wall channels cleanly along H/V strokes while excluding room pastel fills & furniture
    room_color = ((hsv[..., 1] > 16) & (hsv[..., 2] > 135) & (~is_any_blue)).astype(np.uint8)
    room_solid = cv2.morphologyEx(room_color, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    dark = ((gray < 155) & (slab_pad > 0) & (~is_any_blue)).astype(np.uint8)
    line_min = max(16, int(min(h, w) * 0.018))
    lh = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((1, line_min), np.uint8))
    lv = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((line_min, 1), np.uint8))

    wall_bridge = max(13, int(min(h, w) * 0.014)) | 1
    h_walls = cv2.morphologyEx(cv2.morphologyEx(lh, cv2.MORPH_CLOSE, np.ones((wall_bridge, 1), np.uint8)), cv2.MORPH_OPEN, np.ones((4, 1), np.uint8))
    v_walls = cv2.morphologyEx(cv2.morphologyEx(lv, cv2.MORPH_CLOSE, np.ones((1, wall_bridge), np.uint8)), cv2.MORPH_OPEN, np.ones((1, 4), np.uint8))

    # Solid structural pillars + interior acoustic party-wall fills (cyan strips outside clean windows)
    dist = cv2.distanceTransform(dark, cv2.DIST_L2, 3)
    pillars = cv2.dilate((dist >= 1.55).astype(np.uint8), np.ones((3, 3), np.uint8)) & dark
    party_walls = (is_cyan_fill & (~(clean_win > 0))).astype(np.uint8)
    party_walls = cv2.morphologyEx(party_walls, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    thick_all = (h_walls | v_walls | pillars | party_walls) & (~clean_win) & (~room_solid)
    thick_all = cv2.morphologyEx(thick_all, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) & (~clean_win)

    ext_mask = (thick_all & ext_zone.astype(np.uint8)) if ext_zone.any() else thick_all
    int_mask = thick_all & (~ext_mask)

    ext_boxes = [box + [1] for box in _mask_to_clean_boxes(ext_mask, min_len=7, min_area=18)]
    int_boxes = [box + [0] for box in _mask_to_clean_boxes(int_mask, min_len=7, min_area=16)]

    win_h = cv2.morphologyEx(clean_win, cv2.MORPH_OPEN, np.ones((1, 8), np.uint8))
    win_v = cv2.morphologyEx(clean_win & (~win_h), cv2.MORPH_OPEN, np.ones((8, 1), np.uint8))
    win_boxes = _rle_axis_boxes(
        win_h, w, h, transpose=False, min_run=5, max_thick_px=max(16, max_w_thick + 2), min_area=24
    ) + _rle_axis_boxes(
        win_v, w, h, transpose=True, min_run=5, max_thick_px=max(16, max_w_thick + 2), min_area=24
    )

    scene_w, scene_d = compute_plan_real_scale(w, h, regions)
    wall_h = 3.15 if int(floor_number) == 1 else 2.85

    # Compute facade solar exposure per apartment hotspot from nearby outer window directions
    exposures = {}
    for idx, reg in enumerate(regions):
        lx = float(reg.get('label_x') or 50.0)
        ly = float(reg.get('label_y') or 50.0)
        pts = reg.get('polygon_points') or []
        if len(pts) >= 3:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            min_x, max_x = min(xs) - 3.0, max(xs) + 3.0
            min_y, max_y = min(ys) - 3.0, max(ys) + 3.0
            cx = (min(xs) + max(xs)) * 0.5
            cy = (min(ys) + max(ys)) * 0.5
        else:
            min_x, max_x, min_y, max_y, cx, cy = lx - 10, lx + 10, ly - 10, ly + 10, lx, ly

        vx, vy = 0.0, 0.0
        w_cnt = 0
        for wx, wy, ww, wh in win_boxes:
            if min_x <= wx <= max_x and min_y <= wy <= max_y:
                weight = max(ww, wh)
                vx += (wx - cx) * weight
                vy += (wy - cy) * weight
                w_cnt += 1

        if w_cnt > 0 and math.hypot(vx, vy) > 0.5:
            exp_info = _direction_label_from_vector(vx, vy, compass_angle)
        else:
            # Fallback to apartment placement relative to overall floor center
            exp_info = _direction_label_from_vector(cx - 50.0, cy - 50.0, compass_angle)

        key = str(reg.get('apartment_id') or f'reg_{idx}')
        exposures[key] = exp_info

    return {
        'version': 1,
        'floor_number': int(floor_number),
        'wall_height_m': wall_h,
        'scene_width_m': scene_w,
        'scene_depth_m': scene_d,
        'compass_angle': round(float(compass_angle), 1),
        'slab_polygons': slab_polygons,
        'walls': ext_boxes + int_boxes,
        'windows': win_boxes,
        'exposures': exposures,
    }


def rebuild_single_floor_3d(fe) -> bool:
    """Recompute and persist FloorExplorer.geometry_3d for a single FloorExplorer."""
    if not fe.plan_image:
        return False
    rel = fe.plan_image.name
    if not default_storage.exists(rel):
        return False
    with default_storage.open(rel, 'rb') as fh:
        arr = np.frombuffer(fh.read(), dtype=np.uint8)
    plan_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if plan_bgr is None:
        return False

    compass = float(getattr(fe.building_explorer, 'compass_angle', 0.0) or 0.0)
    regions = [
        {
            'apartment_id': hs.apartment_id,
            'total_area': float(hs.apartment.total_area) if hs.apartment_id and hs.apartment else 0.0,
            'polygon_points': hs.polygon_points or [],
            'label_x': hs.label_x,
            'label_y': hs.label_y,
        }
        for hs in fe.hotspots.select_related('apartment').all()
    ]
    fe.geometry_3d = extract_floor_3d_geometry(
        plan_bgr,
        regions,
        floor_number=fe.floor_number,
        compass_angle=compass,
    )
    fe.save(update_fields=['geometry_3d'])
    return True


def rebuild_building_3d_geometry(building_explorer) -> int:
    """Recompute and save FloorExplorer.geometry_3d for every floor that has a plan_image."""
    updated = 0
    for fe in building_explorer.floors.order_by('floor_number'):
        if rebuild_single_floor_3d(fe):
            updated += 1
    return updated

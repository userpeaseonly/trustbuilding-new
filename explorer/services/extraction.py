import io
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from explorer.models import ApartmentHotspot, BuildingExplorer, FloorExplorer
from explorer.services import ai_vision
from explorer.services.spatial_matcher import (
    extract_facade_windows_and_canopy,
    extract_red_keymap_crop,
    slice_multiface_facade,
)

logger = logging.getLogger(__name__)

_RUSSIAN_ORDINALS = {
    'первого': 1, 'первый': 1, '1': 1,
    'второго': 2, 'второй': 2, '2': 2,
    'третьего': 3, 'третий': 3, '3': 3,
    'четвертого': 4, 'четвёртого': 4, 'четвертый': 4, 'четвёртый': 4, '4': 4,
    'пятого': 5, 'пятый': 5, '5': 5,
    'шестого': 6, 'шестой': 6, '6': 6,
    'седьмого': 7, 'седьмой': 7, '7': 7,
    'восьмого': 8, 'восьмой': 8, '8': 8,
    'девятого': 9, 'девятый': 9, '9': 9,
    'десятого': 10, 'десятый': 10, '10': 10,
}

_ROOM_TOKENS = ('комн', 'хона', 'xona', 'room', 'к.')


def linear_sum_assignment_numpy(cost_matrix: np.ndarray) -> tuple[list[int], list[int]]:
    """
    Solve the linear assignment problem on a rectangular cost matrix using pure NumPy
    (O(n^2 * m) Jonker-Volgenant shortest augmenting path), avoiding a SciPy dependency.
    """
    cost = np.asarray(cost_matrix, dtype=np.float64)
    if cost.ndim != 2 or cost.shape[0] == 0 or cost.shape[1] == 0:
        return [], []

    transposed = False
    if cost.shape[0] > cost.shape[1]:
        cost = cost.T
        transposed = True

    n, m = cost.shape
    u = np.zeros(n + 1, dtype=np.float64)
    v = np.zeros(m + 1, dtype=np.float64)
    p = np.zeros(m + 1, dtype=np.int64)
    way = np.zeros(m + 1, dtype=np.int64)
    inf = 1e18

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(m + 1, inf, dtype=np.float64)
        used = np.zeros(m + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = int(p[j0])
            delta = inf
            j1 = 0
            row_cost = cost[i0 - 1]
            for j in range(1, m + 1):
                if not used[j]:
                    cur = float(row_cost[j - 1]) - float(u[i0]) - float(v[j])
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = int(way[j0])
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    pairs = []
    for j in range(1, m + 1):
        if p[j] != 0:
            r_idx = int(p[j] - 1)
            c_idx = j - 1
            if transposed:
                pairs.append((c_idx, r_idx))
            else:
                pairs.append((r_idx, c_idx))
    pairs.sort()
    return [r for r, _ in pairs], [c for _, c in pairs]


def _encode_png_bytes(img_bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode('.png', img_bgr)
    if not ok:
        raise ValueError("Failed to encode PNG image.")
    return buf.tobytes()


def decode_image_bytes(raw_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Unable to decode uploaded image.")
    return img


def slice_facade_into_floors(
    top_left: tuple[float, float],
    top_right: tuple[float, float],
    bottom_right: tuple[float, float],
    bottom_left: tuple[float, float],
    floor_count: int,
    gap_pct: float = 0.03,
) -> dict[int, list[list[float]]]:
    """
    Bilinearly subdivide a quadrilateral into `floor_count` horizontal bands
    (numbered 1 at bottom to `floor_count` at top). Supports perspective renders.
    """
    floor_count = max(1, int(floor_count))
    tl = np.array(top_left, dtype=float)
    tr = np.array(top_right, dtype=float)
    br = np.array(bottom_right, dtype=float)
    bl = np.array(bottom_left, dtype=float)

    bands = {}
    for floor_num in range(1, floor_count + 1):
        # t=0 at bottom edge (floor 1), t=1 at top edge (top floor)
        t0 = (floor_num - 1 + gap_pct) / floor_count
        t1 = (floor_num - gap_pct) / floor_count
        p_bl = bl + t0 * (tl - bl)
        p_br = br + t0 * (tr - br)
        p_tr = br + t1 * (tr - br)
        p_tl = bl + t1 * (tl - bl)
        poly = [
            [round(float(np.clip(p[0], 0.0, 100.0)), 2), round(float(np.clip(p[1], 0.0, 100.0)), 2)]
            for p in (p_tl, p_tr, p_br, p_bl)
        ]
        bands[floor_num] = poly
    return bands


def auto_detect_facade_bands_and_faces(
    render_bgr: np.ndarray,
    floor_count: int,
    *,
    building_label: str = '',
    keymap_bytes: bytes | None = None,
    genplan_bytes: bytes | None = None,
    complex_buildings: list[dict] | None = None,
) -> tuple[dict[int, list[list[float]]], list[dict]]:
    """
    Estimate exterior building facade bounds (key-map & genplan guided multi-face Gemini detection
    when configured, OpenCV architectural edge-envelope fallback otherwise) and slice into floor bands.
    """
    h, w = render_bgr.shape[:2]
    try:
        scale = min(1.0, 1600.0 / max(h, w))
        small = cv2.resize(render_bgr, (int(w * scale), int(h * scale))) if scale < 1.0 else render_bgr
        ai_faces = ai_vision.detect_facade_and_faces_with_ai(
            _encode_png_bytes(small),
            floor_count,
            building_label=building_label,
            keymap_bytes=keymap_bytes,
            genplan_bytes=genplan_bytes,
            complex_buildings=complex_buildings,
        )
    except Exception:
        ai_faces = None

    if ai_faces and ai_faces.get('faces'):
        faces = ai_faces['faces']
        return slice_multiface_facade(faces, floor_count), faces

    gray = cv2.cvtColor(render_bgr, cv2.COLOR_BGR2GRAY)
    gx = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    gy = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    energy = gx + gy

    # Exclude top sky band and foreground parking band when scanning structural density
    y_start = int(h * 0.14)
    y_end = int(h * 0.80)
    x_start = int(w * 0.05)
    x_end = int(w * 0.95)
    band = energy[y_start:y_end, x_start:x_end]

    if band.size > 0 and float(band.max()) > 0:
        row_prof = band.mean(axis=1)
        col_prof = band.mean(axis=0)
        row_thresh = float(np.percentile(row_prof, 40)) * 0.85
        col_thresh = float(np.percentile(col_prof, 25)) * 0.80
        ys = np.where(row_prof >= row_thresh)[0]
        xs = np.where(col_prof >= col_thresh)[0]
        yt = ((y_start + int(ys.min())) / h * 100.0) if len(ys) else 24.0
        yb = ((y_start + int(ys.max())) / h * 100.0) if len(ys) else 76.0
        xl = ((x_start + int(xs.min())) / w * 100.0) if len(xs) else 10.0
        xr = ((x_start + int(xs.max())) / w * 100.0) if len(xs) else 90.0
        xl = max(6.0, min(28.0, xl))
        xr = max(72.0, min(94.0, xr))
        yt = max(18.0, min(38.0, yt))
        yb = max(max(yt + 22.0, 56.0), min(78.0, yb))
    else:
        xl, xr, yt, yb = 10.0, 90.0, 24.0, 76.0

    single_face = [{'tl': [round(xl, 2), round(yt, 2)], 'tr': [round(xr, 2), round(yt, 2)], 'br': [round(xr, 2), round(yb, 2)], 'bl': [round(xl, 2), round(yb, 2)]}]
    return slice_facade_into_floors((xl, yt), (xr, yt), (xr, yb), (xl, yb), floor_count), single_face


def auto_detect_facade_bands(render_bgr: np.ndarray, floor_count: int) -> dict[int, list[list[float]]]:
    """Backward-compatible wrapper returning floor bands dict."""
    bands, _faces = auto_detect_facade_bands_and_faces(render_bgr, floor_count)
    return bands


def _score_street_facade_render(img_bgr: np.ndarray) -> float:
    """
    Distinguish full-height street/courtyard exterior renders (visible sky + balanced structural grid)
    from top-down aerial complex views and close-up entrance lobby crops.
    Optionally refines via AI shot classifier when enabled.
    """
    h, w = img_bgr.shape[:2]
    top_strip = img_bgr[: max(1, int(h * 0.18)), :]
    hsv = cv2.cvtColor(top_strip, cv2.COLOR_BGR2HSV)
    b, _g, r = top_strip[..., 0], top_strip[..., 1], top_strip[..., 2]
    v = hsv[..., 2]
    sky_mask = (b > 135) & (v > 155) & (b.astype(int) >= r.astype(int) - 8)
    sky_ratio = float(sky_mask.mean())
    aspect = min(w / max(h, 1), 2.0) / 2.0
    score = sky_ratio * 10.0 + aspect * 0.5

    # Prefer AI framing classification when key is available so tight lobby closeups never win Hero
    status = ai_vision.get_ai_provider_status()
    if status['gemini_ready'] or status['deepseek_ready']:
        try:
            scale = min(1.0, 640.0 / max(h, w))
            small = cv2.resize(img_bgr, (int(w * scale), int(h * scale))) if scale < 1.0 else img_bgr
            shot = ai_vision.classify_render_shot_with_ai(_encode_png_bytes(small))
            if shot:
                st = shot['shot_type']
                if st == 'full_facade':
                    score += 20.0
                elif st == 'courtyard_wide':
                    score += 8.0
                elif st == 'aerial_complex':
                    score += 2.0
                elif st == 'closeup_detail':
                    score -= 12.0
        except Exception:
            pass
    return score


def _parse_floor_numbers_from_text(text: str, expected_floors: int) -> list[int]:
    if not text:
        return []
    head = "\n".join(text.splitlines()[:20]).lower()
    full_low = text.lower()

    # Check range first: e.g. "2-5 этаж", "2–5 этажи", "2-5 qavat"
    range_m = re.search(r'(\d+)\s*[-–—]\s*(\d+)\s*(?:го\s*)?(?:этаж|qavat|floor)', head)
    if not range_m:
        range_m = re.search(r'план\s+(\d+)\s*[-–—]\s*(\d+)\s*(?:го\s*)?этаж', full_low)
    if range_m:
        a, b = int(range_m.group(1)), int(range_m.group(2))
        if 1 <= a <= b <= max(expected_floors, 30):
            return list(range(a, b + 1))

    # Typical floor e.g. "План типового этажа"
    if re.search(r'типово\w*\s+этаж|typical\s+floor|tipovoy', head):
        return list(range(2, max(2, expected_floors) + 1))

    # Specific ordinal / numbered floor title: "План первого этажа", "План 2-го этажа", "3-qavat", "Floor 4"
    patterns = [
        r'(?:план\s+)?(первого|второго|третьего|четвертого|четвёртого|пятого|шестого|седьмого|восьмого|девятого|десятого)\s+этаж',
        r'(?:план\s+)?(\d+)\s*[-–]?\s*(?:го|й)?\s*этаж',
        r'(\d+)\s*[-–]?\s*qavat',
        r'floor\s*#?\s*(\d+)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, head):
            tok = m.group(1).strip()
            fl = _RUSSIAN_ORDINALS.get(tok)
            if fl is None and tok.isdigit():
                fl = int(tok)
            if fl and 1 <= fl <= max(expected_floors, 30):
                return [fl]

    # Retry across full text for specific floor heading if not in top lines
    for pat in patterns[:2]:
        m = re.search(pat, full_low)
        if m:
            tok = m.group(1).strip()
            fl = _RUSSIAN_ORDINALS.get(tok) or (int(tok) if tok.isdigit() else None)
            if fl and 1 <= fl <= max(expected_floors, 30):
                return [fl]
    return []


def classify_pdf_pages(pdf_path: str, expected_floors: int) -> dict:
    """
    Analyze an architectural PDF album using pdfinfo + pdftotext + pdfimages.
    Returns {
      "num_pages": int,
      "floor_pages": {page_num: [floor_nums]},
      "render_pages": [page_num, ...],
      "masterplan_pages": [page_num, ...],
      "page_images": {page_num: [{"width": int, "height": int}, ...]},
    }
    """
    info_out = subprocess.check_output(['pdfinfo', pdf_path], text=True, stderr=subprocess.DEVNULL)
    pm = re.search(r'Pages:\s+(\d+)', info_out)
    num_pages = int(pm.group(1)) if pm else 0

    img_out = subprocess.check_output(['pdfimages', '-list', pdf_path], text=True, stderr=subprocess.DEVNULL)
    page_images: dict[int, list[dict]] = {}
    for line in img_out.splitlines()[2:]:
        parts = line.split()
        if len(parts) >= 5 and parts[0].isdigit():
            pnum = int(parts[0])
            w_px, h_px = int(parts[3]), int(parts[4])
            page_images.setdefault(pnum, []).append({'width': w_px, 'height': h_px, 'pixels': w_px * h_px})

    floor_pages: dict[int, list[int]] = {}
    render_pages: list[int] = []
    masterplan_pages: list[int] = []
    unclassified_visual: list[int] = []

    for pnum in range(1, num_pages + 1):
        txt = subprocess.check_output(
            ['pdftotext', '-f', str(pnum), '-l', str(pnum), pdf_path, '-'],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        stripped = txt.strip()
        imgs = page_images.get(pnum, [])
        max_pixels = max((im['pixels'] for im in imgs), default=0)

        # Page 1 covers often have a small render + title text
        if pnum == 1 and re.search(r'альбом|проект\s+строительства|loyiha', stripped, re.IGNORECASE):
            continue

        if re.search(r'ген\s*план|генеральный\s+план|master\s*plan|bosh\s+reja', stripped, re.IGNORECASE):
            masterplan_pages.append(pnum)
            continue

        floors = _parse_floor_numbers_from_text(stripped, expected_floors)
        if floors:
            floor_pages[pnum] = floors
            continue

        if re.search(r'общий\s+вид|фасад|3d|рендер|umumiy\s+ko\'rinish|exterior', stripped, re.IGNORECASE) or (
            max_pixels >= 450_000 and len(stripped) < 250
        ):
            render_pages.append(pnum)
            continue

        if max_pixels >= 450_000 and len(stripped) < 100:
            unclassified_visual.append(pnum)

    # Fallback: use DeepSeek Vision on scanned/image-only pages if enabled
    if unclassified_visual and getattr(ai_vision.settings, 'AI_ENABLED', False):
        with tempfile.TemporaryDirectory() as td:
            for pnum in unclassified_visual:
                out_prefix = os.path.join(td, f'cls_{pnum}')
                subprocess.check_call(
                    ['pdftoppm', '-r', '60', '-f', str(pnum), '-l', str(pnum), '-singlefile', '-png', pdf_path, out_prefix],
                    stderr=subprocess.DEVNULL,
                )
                png_bytes = Path(f'{out_prefix}.png').read_bytes()
                cls = ai_vision.classify_page_with_ai(png_bytes, pnum, expected_floors)
                if cls:
                    if cls['kind'] == 'render':
                        render_pages.append(pnum)
                    elif cls['kind'] == 'masterplan':
                        masterplan_pages.append(pnum)
                    elif cls['kind'] == 'floor_plan' and cls.get('floors'):
                        floor_pages[pnum] = [int(f) for f in cls['floors'] if isinstance(f, (int, float)) or str(f).isdigit()]

    return {
        'num_pages': num_pages,
        'floor_pages': floor_pages,
        'render_pages': render_pages,
        'masterplan_pages': masterplan_pages,
        'page_images': page_images,
    }


def _extract_largest_image_on_page(pdf_path: str, page_num: int, out_dir: str) -> np.ndarray | None:
    """
    Render a PDF presentation page with Poppler (respecting PDF page /Rotate and CTM
    transforms automatically) and trim outer borders/headers to isolate the 3D render.
    """
    prefix = os.path.join(out_dir, f'rend_p{page_num}')
    subprocess.check_call(
        ['pdftoppm', '-r', '140', '-f', str(page_num), '-l', str(page_num), '-singlefile', '-png', pdf_path, prefix],
        stderr=subprocess.DEVNULL,
    )
    img = cv2.imread(f'{prefix}.png')
    if img is None:
        return None

    h, w = img.shape[:2]
    # Trim thin outer PDF border frame and title strip, then isolate the main photo rectangle
    sub = img[int(h * 0.05): int(h * 0.97), int(w * 0.02): int(w * 0.98)]
    sh, sw = sub.shape[:2]
    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    non_white = (gray < 248).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(non_white, 8)
    if n > 1:
        best_i = max(range(1, n), key=lambda i: int(st[i, cv2.CC_STAT_AREA]))
        area = int(st[best_i, cv2.CC_STAT_AREA])
        if area >= 0.25 * sh * sw:
            x, y, bw, bh = (
                int(st[best_i, cv2.CC_STAT_LEFT]),
                int(st[best_i, cv2.CC_STAT_TOP]),
                int(st[best_i, cv2.CC_STAT_WIDTH]),
                int(st[best_i, cv2.CC_STAT_HEIGHT]),
            )
            pad = 3 if (bw > 20 and bh > 20) else 0
            return sub[y + pad: y + bh - pad, x + pad: x + bw - pad].copy()
    return img


def make_clean_architectural_blueprint(img_bgr: np.ndarray) -> np.ndarray:
    """
    Convert pastel-colored CAD room fills into a crisp, high-contrast architectural monochrome
    blueprint (pure white room paper + sharp dark CAD walls, doors, text, and dimensions)
    so that only status overlays (Emerald = Free to Sell, Slate/Rose = Sold) color the plan.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    k_bg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, k_bg)
    bg = cv2.GaussianBlur(bg, (15, 15), 0).astype(np.float32)
    norm = np.clip((gray.astype(np.float32) / np.maximum(bg, 40.0)) * 255.0, 0, 255).astype(np.uint8)
    norm = np.clip((norm.astype(np.float32) - 255.0) * 1.15 + 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(norm, cv2.COLOR_GRAY2BGR)


def refine_and_orthogonalize_region_mask(
    sub_fm: np.ndarray,
    cw: int,
    ch: int,
) -> tuple[list[list[float]], float, float, np.ndarray]:
    """
    Bridge across interior room partition walls, doorways, and number circles inside an apartment
    mask to produce a unified, 90-degree rectilinear outer perimeter polygon and centered label anchor.
    Explicitly pads with 0 borders and clamps to the original region bounding box so morphology never
    bleeds to the image edges.
    """
    m = (sub_fm > 0).astype(np.uint8) * 255
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return [], 50.0, 50.0, (m > 0).astype(np.uint8)
    bx0, by0, bx1, by1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1

    pad = 80
    mp = cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)

    close_sz = max(25, int(round(min(cw, ch) * 0.082)) | 1)
    k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (close_sz, close_sz))
    mp_closed = cv2.morphologyEx(mp, cv2.MORPH_CLOSE, k_close, borderType=cv2.BORDER_CONSTANT, borderValue=0)

    cnts, _ = cv2.findContours(mp_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mp_solid = np.zeros_like(mp)
    if cnts:
        cv2.drawContours(mp_solid, [max(cnts, key=cv2.contourArea)], -1, 255, thickness=cv2.FILLED)
    else:
        mp_solid = mp

    open_sz = max(9, int(round(min(cw, ch) * 0.022)) | 1)
    mp_rect = cv2.morphologyEx(
        mp_solid,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (open_sz, open_sz)),
        borderType=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    m_rect = mp_rect[pad:pad + ch, pad:pad + cw].copy()

    # Clamp strictly to the original apartment bounding box so it never expands outside outer walls
    bbox_mask = np.zeros_like(m_rect)
    bbox_mask[by0:by1, bx0:bx1] = 255
    m_rect &= bbox_mask

    cnts2, _ = cv2.findContours(m_rect, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts2:
        m_rect = m
        cnts2, _ = cv2.findContours(m_rect, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts2:
        return [], 50.0, 50.0, (m_rect > 0).astype(np.uint8)

    largest = max(cnts2, key=cv2.contourArea)
    peri = cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, 0.006 * peri, True)
    pts = [[float(p[0][0]), float(p[0][1])] for p in approx]

    if len(pts) >= 4:
        for _ in range(2):
            n = len(pts)
            for i in range(n):
                p1 = pts[i]
                p2 = pts[(i + 1) % n]
                dx = abs(p2[0] - p1[0])
                dy = abs(p2[1] - p1[1])
                if dx < dy * 0.22:
                    avg_x = (p1[0] + p2[0]) / 2.0
                    p1[0] = avg_x
                    p2[0] = avg_x
                elif dy < dx * 0.22:
                    avg_y = (p1[1] + p2[1]) / 2.0
                    p1[1] = avg_y
                    p2[1] = avg_y

        cleaned = []
        n = len(pts)
        for i in range(n):
            p_prev = pts[(i - 1) % n]
            p_cur = pts[i]
            p_next = pts[(i + 1) % n]
            v1 = (p_cur[0] - p_prev[0], p_cur[1] - p_prev[1])
            v2 = (p_next[0] - p_cur[0], p_next[1] - p_cur[1])
            l1 = np.hypot(*v1)
            l2 = np.hypot(*v2)
            if l1 < 4 or l2 < 4:
                continue
            cross = abs(v1[0] * v2[1] - v1[1] * v2[0]) / (l1 * l2)
            if cross > 0.12:
                cleaned.append(p_cur)
        if len(cleaned) >= 4:
            pts = cleaned

    pts_pct = [
        [round(float(np.clip(p[0] / cw * 100.0, 0.0, 100.0)), 2), round(float(np.clip(p[1] / ch * 100.0, 0.0, 100.0)), 2)]
        for p in pts
    ]
    dist_mask = (m_rect > 0).astype(np.uint8)
    dist_mask[0, :] = 0
    dist_mask[-1, :] = 0
    dist_mask[:, 0] = 0
    dist_mask[:, -1] = 0
    dist_in = cv2.distanceTransform(dist_mask, cv2.DIST_L2, 5)
    ly, lx = np.unravel_index(int(np.argmax(dist_in)), dist_in.shape)
    lx_pct = round(float(np.clip(lx / cw * 100.0, 10.0, 90.0)), 2)
    ly_pct = round(float(np.clip(ly / ch * 100.0, 10.0, 90.0)), 2)
    return pts_pct, lx_pct, ly_pct, (m_rect > 0).astype(np.uint8)


def segment_floor_plan(img_bgr: np.ndarray) -> dict:
    """
    Detect colored apartment polygons (with monochrome blueprint fallback), compute smart crop
    around the floor drawing, simplify SVG contours in 0..100 coordinates of the cropped image,
    and compute interior label anchors via distance transform.
    """
    h, w = img_bgr.shape[:2]
    area_scale = (h * w) / (1655.0 * 1170.0)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1], hsv[..., 2]

    mask = ((s > 22) & (v > 140)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

    px = img_bgr[mask > 0].reshape(-1, 3).astype(np.int32)
    regions = []

    if len(px) > 0:
        q = (px // 6) * 6 + 3
        keys, counts = np.unique(q, axis=0, return_counts=True)
        order = np.argsort(-counts)
        min_color_px = max(250, int(400 * area_scale))
        centers = []
        for i in order:
            if int(counts[i]) < min_color_px:
                break
            c = keys[i]
            if all(np.linalg.norm(c - k) > 14.0 for k in centers):
                centers.append(c)

        bridge = max(7, int(round(min(h, w) * 0.0077)))
        if bridge % 2 == 0:
            bridge += 1
        k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (bridge, bridge))
        min_comp_area = max(500, int(900 * area_scale))

        for c in centers:
            m = ((np.linalg.norm(img_bgr.astype(np.int32) - c, axis=2) <= 14.0) & (mask > 0)).astype(np.uint8)
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k_close)
            n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
            for idx in range(1, n):
                comp_area = int(st[idx, cv2.CC_STAT_AREA])
                if comp_area >= min_comp_area:
                    regions.append({
                        'color_bgr': c,
                        'area': comp_area,
                        'mask': (lab == idx).astype(np.uint8),
                    })

        total_area = sum(r['area'] for r in regions) or 1
        regions = [r for r in regions if (r['area'] / total_area) >= 0.04]

    # Fallback for uncolored monochrome floor plans
    if len(regions) < 2:
        regions = _segment_monochrome_fallback(img_bgr)

    regions.sort(key=lambda r: -r['area'])

    # Compute filled exterior masks & distance maps BEFORE cropping (for accurate PDF word matching)
    full_filled_masks = []
    full_dist_maps = []
    union_mask = np.zeros((h, w), dtype=np.uint8)

    for r in regions:
        cnts, _ = cv2.findContours(r['mask'], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        fm = np.zeros((h, w), dtype=np.uint8)
        if cnts:
            cv2.drawContours(fm, cnts, -1, 1, thickness=cv2.FILLED)
        full_filled_masks.append(fm)
        full_dist_maps.append(cv2.distanceTransform(1 - fm, cv2.DIST_L2, 5))
        union_mask |= fm

    # Smart crop tightly around plan regions (+8% margin so axis grids remain readable)
    if union_mask.any():
        ys, xs = np.nonzero(union_mask)
        ux1, uy1, ux2, uy2 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
        pad_x = max(20, int((ux2 - ux1) * 0.08))
        pad_y = max(20, int((uy2 - uy1) * 0.08))
        cx1 = max(0, ux1 - pad_x)
        cy1 = max(0, uy1 - pad_y)
        cx2 = min(w, ux2 + pad_x)
        cy2 = min(h, uy2 + pad_y)
    else:
        cx1, cy1, cx2, cy2 = 0, 0, w, h

    raw_crop_img = img_bgr[cy1:cy2, cx1:cx2].copy()
    crop_img = make_clean_architectural_blueprint(raw_crop_img)
    cw = max(1, cx2 - cx1)
    ch = max(1, cy2 - cy1)

    cropped_regions = []
    for i, (r, fm) in enumerate(zip(regions, full_filled_masks)):
        sub_fm = fm[cy1:cy2, cx1:cx2]
        pts, lx_pct, ly_pct, refined_sub = refine_and_orthogonalize_region_mask(sub_fm, cw, ch)
        if len(pts) < 3:
            continue
        full_filled_masks[i][cy1:cy2, cx1:cx2] = refined_sub
        full_dist_maps[i] = cv2.distanceTransform(1 - full_filled_masks[i], cv2.DIST_L2, 5)
        cropped_regions.append({
            'area': r['area'],
            'polygon_points': pts,
            'label_x': lx_pct,
            'label_y': ly_pct,
        })

    return {
        'full_width': w,
        'full_height': h,
        'crop_box': (cx1, cy1, cx2, cy2),
        'crop_img': crop_img,
        'crop_width': cw,
        'crop_height': ch,
        'regions': cropped_regions,
        'full_filled_masks': full_filled_masks,
        'full_dist_maps': full_dist_maps,
    }


def _segment_monochrome_fallback(img_bgr: np.ndarray) -> list[dict]:
    """Basic morphological enclosure detection for black-and-white uncolored CAD drawings."""
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    walls = (gray < 175).astype(np.uint8)
    door_seal = max(11, int(round(min(h, w) * 0.011)) | 1)
    closed_walls = cv2.morphologyEx(walls, cv2.MORPH_CLOSE, np.ones((door_seal, door_seal), np.uint8))
    open_spaces = 1 - closed_walls
    n, lab, st, _ = cv2.connectedComponentsWithStats(open_spaces, 4)
    img_area = float(h * w)
    out = []
    for idx in range(1, n):
        area = int(st[idx, cv2.CC_STAT_AREA])
        frac = area / img_area
        if 0.008 <= frac <= 0.22:
            out.append({'area': area, 'mask': (lab == idx).astype(np.uint8)})
    return out


def _render_numbered_overlay(crop_img: np.ndarray, regions: list[dict]) -> bytes:
    vis = crop_img.copy()
    ch, cw = vis.shape[:2]
    palette = [
        (34, 197, 94), (59, 130, 246), (249, 115, 22), (168, 85, 247),
        (236, 72, 153), (20, 184, 166), (234, 179, 8), (239, 68, 68),
    ]
    for idx, reg in enumerate(regions, 1):
        pts = np.array([[int(p[0] / 100.0 * cw), int(p[1] / 100.0 * ch)] for p in reg['polygon_points']], dtype=np.int32)
        col = palette[(idx - 1) % len(palette)]
        cv2.polylines(vis, [pts], True, col, 3)
        cx = int(reg['label_x'] / 100.0 * cw)
        cy = int(reg['label_y'] / 100.0 * ch)
        cv2.circle(vis, (cx, cy), 22, (15, 23, 42), -1)
        cv2.putText(vis, str(idx), (cx - 10, cy + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2, cv2.LINE_AA)
    return _encode_png_bytes(vis)


def _extract_pdf_words(pdf_path: str, page_num: int, full_w: int, full_h: int) -> list[tuple[float, float, str]]:
    xml_out = subprocess.check_output(
        ['pdftotext', '-bbox', '-f', str(page_num), '-l', str(page_num), pdf_path, '-'],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    pm = re.search(r'<page width="([\d.]+)" height="([\d.]+)">', xml_out)
    if not pm:
        return []
    pw, ph = float(pm.group(1)), float(pm.group(2))
    # Handle rotated PDF MediaBox vs visual rendered image dimensions
    if (full_w > full_h) != (pw > ph):
        pw, ph = ph, pw

    words = []
    for wm in re.finditer(
        r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]+)</word>',
        xml_out,
    ):
        x1, y1, x2, y2, txt = float(wm.group(1)), float(wm.group(2)), float(wm.group(3)), float(wm.group(4)), wm.group(5).strip()
        cx = (x1 + x2) / 2.0 / pw * full_w
        cy = (y1 + y2) / 2.0 / ph * full_h
        words.append((cx, cy, txt))
    return words


def match_regions_to_apartments(
    seg: dict,
    db_apartments: list,
    pdf_path: str | None = None,
    page_num: int | None = None,
) -> dict[int, tuple]:
    """
    Match extracted polygon indices (0-based into `seg['regions']`) to `Apartment` model instances.
    Uses Tier 1 (PDF bbox + Hungarian), Tier 2 (DeepSeek Vision fallback), and Tier 3 (unique area rank).
    Returns {region_idx: (Apartment, confidence_label)}.
    """
    regions = seg['regions']
    if not regions or not db_apartments:
        return {}

    matched: dict[int, tuple] = {}
    used_apt_ids = set()

    # Tier 1: Deterministic PDF vector text coordinates + NumPy Hungarian matching
    if pdf_path and page_num:
        full_w, full_h = seg['full_width'], seg['full_height']
        words = _extract_pdf_words(pdf_path, page_num, full_w, full_h)
        cx1, cy1, cx2, cy2 = seg['crop_box']
        margin = max(60.0, full_w * 0.04)
        plan_words = [
            (cx, cy, txt)
            for (cx, cy, txt) in words
            if (cx1 - margin) <= cx <= (cx2 + margin) and (cy1 - margin) <= cy <= (cy2 + margin)
        ]

        if plan_words:
            dist_maps = seg['full_dist_maps'][: len(regions)]
            n_r, n_a = len(regions), len(db_apartments)
            cost = np.full((n_r, n_a), 1e6, dtype=np.float64)
            num_cutoff = max(80.0, full_w * 0.05)
            area_cutoff = max(20.0, full_w * 0.015)

            for ri, dist in enumerate(dist_maps):
                for ai, apt in enumerate(db_apartments):
                    num_s = str(apt.apartment_number).strip()
                    area_s = str(apt.total_area)
                    area_short = area_s.rstrip('0').rstrip('.')
                    area_variants = {area_s, area_short, area_s.replace('.', ','), area_short.replace('.', ',')}

                    area_d = min(
                        (
                            float(dist[min(full_h - 1, max(0, int(cy))), min(full_w - 1, max(0, int(cx)))])
                            for (cx, cy, txt) in plan_words
                            if txt in area_variants
                        ),
                        default=999.0,
                    )

                    num_cands = []
                    for (cx, cy, txt) in plan_words:
                        if txt == num_s:
                            is_room_label = any(
                                any(t2.lower().startswith(rt) for rt in _ROOM_TOKENS)
                                and abs(cy2_w - cy) < max(10.0, full_h * 0.01)
                                and 0.0 < (cx2_w - cx) < max(60.0, full_w * 0.045)
                                for (cx2_w, cy2_w, t2) in plan_words
                            )
                            if not is_room_label:
                                py = min(full_h - 1, max(0, int(cy)))
                                px = min(full_w - 1, max(0, int(cx)))
                                num_cands.append(float(dist[py, px]))

                    num_d = min(num_cands, default=999.0)
                    score = 0.0
                    if num_d < num_cutoff:
                        score -= (100.0 - num_d) * 2.0
                    if area_d < area_cutoff:
                        score -= (50.0 - area_d) * 1.5
                    cost[ri, ai] = score

            row_ind, col_ind = linear_sum_assignment_numpy(cost)
            for r_idx, c_idx in zip(row_ind, col_ind):
                if cost[r_idx, c_idx] < -20.0:
                    apt = db_apartments[c_idx]
                    matched[r_idx] = (apt, f'PDF #{apt.apartment_number}')
                    used_apt_ids.add(apt.pk)

    # Tier 2: DeepSeek / OpenAI-compatible Vision AI fallback for image uploads or remaining unmatched regions
    remaining_reg = [i for i in range(len(regions)) if i not in matched]
    remaining_apts = [a for a in db_apartments if a.pk not in used_apt_ids]

    if remaining_reg and remaining_apts:
        overlay_bytes = _render_numbered_overlay(seg['crop_img'], regions)
        apt_payload = [
            {
                'apartment_number': str(a.apartment_number),
                'total_area': str(a.total_area),
                'rooms': a.living_room_count,
            }
            for a in remaining_apts
        ]
        ai_matches = ai_vision.match_regions_with_ai(overlay_bytes, apt_payload)
        if ai_matches:
            apt_lookup = {str(a.apartment_number): a for a in remaining_apts}
            for reg_1_based, apt_num in ai_matches.items():
                ri = reg_1_based - 1
                if ri in remaining_reg and apt_num in apt_lookup:
                    apt = apt_lookup[apt_num]
                    if apt.pk not in used_apt_ids:
                        matched[ri] = (apt, f'AI #{apt.apartment_number}')
                        used_apt_ids.add(apt.pk)

    # Tier 3: Deterministic last-resort match if counts match cleanly (e.g. single leftover unit)
    remaining_reg = [i for i in range(len(regions)) if i not in matched]
    remaining_apts = [a for a in db_apartments if a.pk not in used_apt_ids]
    if len(remaining_reg) == 1 and len(remaining_apts) == 1:
        apt = remaining_apts[0]
        matched[remaining_reg[0]] = (apt, f'Auto #{apt.apartment_number}')

    return matched


def _save_png_to_field(field_file, img_bgr: np.ndarray, filename: str) -> tuple[int, int]:
    png_bytes = _encode_png_bytes(img_bgr)
    field_file.save(filename, ContentFile(png_bytes), save=False)
    h, w = img_bgr.shape[:2]
    return int(w), int(h)


def apply_floor_plan_extraction(
    building_explorer: BuildingExplorer,
    floor_numbers: list[int],
    plan_bgr: np.ndarray,
    pdf_path: str | None = None,
    page_num: int | None = None,
) -> dict:
    """
    Segment `plan_bgr` once and save FloorExplorer + matched ApartmentHotspots
    for each target floor in `floor_numbers`.
    """
    seg = segment_floor_plan(plan_bgr)
    regions = seg['regions']
    crop_img = seg['crop_img']
    ch, cw = crop_img.shape[:2]
    crop_png_bytes = _encode_png_bytes(crop_img)

    building = building_explorer.building
    summary = {}

    for fl in floor_numbers:
        floor_exp, _ = FloorExplorer.objects.get_or_create(
            building_explorer=building_explorer,
            floor_number=fl,
        )
        filename = f'b{building.pk}_f{fl}.png'
        floor_exp.plan_image.save(filename, ContentFile(crop_png_bytes), save=False)
        floor_exp.plan_width = cw
        floor_exp.plan_height = ch
        floor_exp.save()

        db_apts = list(
            building.apartments.filter(is_real=True, floor_number=fl).order_by('id')
        )
        matched = match_regions_to_apartments(seg, db_apts, pdf_path=pdf_path, page_num=page_num)

        floor_exp.hotspots.all().delete()
        hotspots_to_create = []
        regions_for_3d = []
        for idx, reg in enumerate(regions):
            apt_pair = matched.get(idx)
            apt = apt_pair[0] if apt_pair else None
            label = apt_pair[1] if apt_pair else f'Region {idx + 1}'
            hotspots_to_create.append(
                ApartmentHotspot(
                    floor_explorer=floor_exp,
                    apartment=apt,
                    polygon_points=reg['polygon_points'],
                    label_x=reg['label_x'],
                    label_y=reg['label_y'],
                    detected_label=label,
                )
            )
            regions_for_3d.append({
                'apartment_id': apt.pk if apt else None,
                'total_area': float(apt.total_area) if apt else 0.0,
                'polygon_points': reg['polygon_points'],
                'label_x': reg['label_x'],
                'label_y': reg['label_y'],
            })
        ApartmentHotspot.objects.bulk_create(hotspots_to_create)
        summary[str(fl)] = {
            'regions': len(regions),
            'matched': len(matched),
            'expected': len(db_apts),
        }
    return summary


@transaction.atomic
def extract_building_from_pdf(building_explorer: BuildingExplorer, pdf_path: str) -> dict:
    """
    Run the full end-to-end PDF album extraction for a BuildingExplorer:
      1. Classify cover / masterplan / floor plans / 3D renders
      2. Extract exterior renders & pick best street-level hero render
      3. Generate horizontal/perspective floor facade bands on hero render
      4. Segment & match all floor plans (1..floor_count) against DB apartments
    """
    building = building_explorer.building
    building_explorer.extraction_status = BuildingExplorer.STATUS_PROCESSING
    building_explorer.save(update_fields=['extraction_status', 'updated_at'])

    try:
        classification = classify_pdf_pages(pdf_path, expected_floors=building.floor_count)

        with tempfile.TemporaryDirectory() as td:
            # 1. Extract render images and choose hero render (highest street-level sky score)
            render_candidates = []
            extra_renders = []

            for pnum in classification['render_pages']:
                img_bgr = _extract_largest_image_on_page(pdf_path, pnum, td)
                if img_bgr is None:
                    continue
                score = _score_street_facade_render(img_bgr)
                rh, rw = img_bgr.shape[:2]
                rel_name = f'explorer/renders/b{building.pk}_view_p{pnum}.png'
                if default_storage.exists(rel_name):
                    default_storage.delete(rel_name)
                saved_path = default_storage.save(rel_name, ContentFile(_encode_png_bytes(img_bgr)))
                extra_renders.append({
                    'path': saved_path,
                    'label': f'View {len(extra_renders) + 1} (p.{pnum})',
                    'width': int(rw),
                    'height': int(rh),
                    'sky_score': round(score, 2),
                })
                render_candidates.append((score, img_bgr, saved_path))

            # Optional masterplan extraction saved in extra_renders too for Complex reuse
            masterplan_rel = ''
            masterplan_bytes = None
            for pnum in classification['masterplan_pages']:
                mp_prefix = os.path.join(td, f'mp_{pnum}')
                subprocess.check_call(
                    ['pdftoppm', '-r', '130', '-f', str(pnum), '-l', str(pnum), '-singlefile', '-png', pdf_path, mp_prefix],
                    stderr=subprocess.DEVNULL,
                )
                mp_bgr = cv2.imread(f'{mp_prefix}.png')
                if mp_bgr is not None:
                    mh, mw = mp_bgr.shape[:2]
                    mp_raw = _encode_png_bytes(mp_bgr)
                    rel_mp = f'explorer/renders/b{building.pk}_masterplan_p{pnum}.png'
                    if default_storage.exists(rel_mp):
                        default_storage.delete(rel_mp)
                    saved_mp = default_storage.save(rel_mp, ContentFile(mp_raw))
                    if not masterplan_rel:
                        masterplan_rel = saved_mp
                        masterplan_bytes = mp_raw
                        comp_deg = ai_vision.extract_compass_with_ai(mp_raw)
                        if comp_deg is not None:
                            building_explorer.compass_angle = comp_deg
                    extra_renders.append({
                        'path': saved_mp,
                        'label': f'Masterplan (p.{pnum})',
                        'width': int(mw),
                        'height': int(mh),
                        'sky_score': -1.0,
                    })

            building_explorer.extra_renders = extra_renders

            # 2. Extract floor plans, polygons & corner key-map (before Hero Render selection so AI knows which block this is!)
            floor_results = {}
            all_covered_floors = set()
            keymap_rel = ''
            keymap_bytes = None

            for pnum, floors in sorted(classification['floor_pages'].items()):
                fp_prefix = os.path.join(td, f'fp_{pnum}')
                subprocess.check_call(
                    ['pdftoppm', '-r', '140', '-f', str(pnum), '-l', str(pnum), '-singlefile', '-png', pdf_path, fp_prefix],
                    stderr=subprocess.DEVNULL,
                )
                plan_bgr = cv2.imread(f'{fp_prefix}.png')
                if plan_bgr is None:
                    continue
                if not keymap_rel:
                    km_bytes = extract_red_keymap_crop(plan_bgr)
                    if km_bytes:
                        keymap_bytes = km_bytes
                        rel_km = f'explorer/keymaps/b{building.pk}_keymap.png'
                        if default_storage.exists(rel_km):
                            default_storage.delete(rel_km)
                        keymap_rel = default_storage.save(rel_km, ContentFile(km_bytes))
                res = apply_floor_plan_extraction(
                    building_explorer,
                    floor_numbers=floors,
                    plan_bgr=plan_bgr,
                    pdf_path=pdf_path,
                    page_num=pnum,
                )
                floor_results.update(res)
                all_covered_floors.update(floors)

            # 3. Choose best Hero Render for THIS target block (Key-Map guided comparative AI selection)
            b_label = f"{building.name} (Block {building.block_number})" if building.block_number else building.name
            siblings = [
                {'id': sb.pk, 'name': sb.name, 'block_number': sb.block_number or '', 'floor_count': sb.floor_count}
                for sb in building.company.buildings.all().order_by('block_number', 'id')
            ]
            hero_bgr = None
            if render_candidates:
                chosen_item = None
                if len(render_candidates) >= 2 and (ai_vision.get_ai_provider_status()['gemini_ready'] or ai_vision.get_ai_provider_status()['deepseek_ready']):
                    ai_pick = ai_vision.select_best_hero_render_with_ai(
                        [(i, _encode_png_bytes(c[1])) for i, c in enumerate(render_candidates)],
                        block_label=b_label,
                        keymap_bytes=keymap_bytes,
                        genplan_bytes=masterplan_bytes,
                    )
                    if ai_pick and 0 <= ai_pick['best_index'] < len(render_candidates):
                        chosen_item = render_candidates[ai_pick['best_index']]
                if chosen_item is None:
                    render_candidates.sort(key=lambda item: -item[0])
                    chosen_item = render_candidates[0]
                hero_bgr = chosen_item[1]
                hw, hh = _save_png_to_field(building_explorer.hero_render, hero_bgr, f'b{building.pk}_hero.png')
                building_explorer.hero_width = hw
                building_explorer.hero_height = hh

            # 4. Assign target-isolated multi-face floor bands + extract glass windows & foreground foliage cutout
            if hero_bgr is not None:
                bands, faces = auto_detect_facade_bands_and_faces(
                    hero_bgr,
                    building.floor_count,
                    building_label=b_label,
                    keymap_bytes=keymap_bytes,
                    genplan_bytes=masterplan_bytes,
                    complex_buildings=siblings,
                )
                building_explorer.facade_faces = faces
                win_canopy = extract_facade_windows_and_canopy(hero_bgr, bands, rel_prefix=f'b{building.pk}_hero')
            else:
                bands = slice_facade_into_floors((10.0, 22.0), (90.0, 22.0), (90.0, 78.0), (10.0, 78.0), building.floor_count)
                win_canopy = {'windows_by_floor': {}, 'canopy_path': ''}

            ai_meta = dict(building_explorer.ai_metadata or {})
            if keymap_rel:
                ai_meta['keymap_path'] = keymap_rel
            if masterplan_rel:
                ai_meta['masterplan_path'] = masterplan_rel
            ai_meta['windows_by_floor'] = win_canopy['windows_by_floor']
            ai_meta['canopy_path'] = win_canopy['canopy_path']
            building_explorer.ai_metadata = ai_meta
            building_explorer.save(update_fields=['ai_metadata'])

            if hero_bgr is not None and building_explorer.atmosphere_enabled and ai_vision.get_ai_provider_status().get('gemini_ready'):
                try:
                    from explorer.services.spatial_matcher import generate_building_atmosphere_renders
                    generate_building_atmosphere_renders(building_explorer, save_model=True)
                except Exception as exc:
                    logger.warning("AI atmosphere generation skipped cleanly during PDF extract: %s", exc)

            for fl in range(1, building.floor_count + 1):
                floor_exp, _ = FloorExplorer.objects.get_or_create(
                    building_explorer=building_explorer,
                    floor_number=fl,
                )
                if fl in bands:
                    floor_exp.facade_polygon = bands[fl]
                    floor_exp.save(update_fields=['facade_polygon'])

        total_matched = sum(v['matched'] for v in floor_results.values())
        total_expected = sum(v['expected'] for v in floor_results.values())
        summary = {
            'pages_total': classification['num_pages'],
            'render_count': len([r for r in extra_renders if r.get('sky_score', 0) >= 0]),
            'floors_extracted': sorted(all_covered_floors),
            'matched_apartments': total_matched,
            'expected_apartments': total_expected,
            'per_floor': floor_results,
        }
        building_explorer.extraction_status = BuildingExplorer.STATUS_READY
        building_explorer.extraction_summary = summary
        building_explorer.save()
        return summary

    except Exception as exc:
        logger.exception("PDF extraction failed for Building %s: %s", building.pk, exc)
        building_explorer.extraction_status = BuildingExplorer.STATUS_FAILED
        building_explorer.extraction_summary = {'error': str(exc)}
        building_explorer.save(update_fields=['extraction_status', 'extraction_summary', 'updated_at'])
        raise


def copy_floor_layout_to_targets(
    source_floor: FloorExplorer,
    target_floors: list[FloorExplorer],
) -> int:
    """
    Copy apartment hotspots & cropped plan image from `source_floor` to each `target_floor`,
    automatically mapping each polygon to the corresponding target-floor Apartment by position/area.
    """
    src_hotspots = list(source_floor.hotspots.select_related('apartment').order_by('id'))
    if not src_hotspots:
        return 0

    src_apts_ordered = list(
        source_floor.building_explorer.building.apartments.filter(
            is_real=True, floor_number=source_floor.floor_number
        ).order_by('id')
    )
    src_rank_by_pk = {a.pk: idx for idx, a in enumerate(src_apts_ordered)}

    updated_count = 0
    for tf in target_floors:
        if tf.pk == source_floor.pk:
            continue
        if source_floor.plan_image and not tf.plan_image:
            tf.plan_image = source_floor.plan_image
            tf.plan_width = source_floor.plan_width
            tf.plan_height = source_floor.plan_height
            tf.save(update_fields=['plan_image', 'plan_width', 'plan_height'])

        target_apts = list(
            tf.building_explorer.building.apartments.filter(
                is_real=True, floor_number=tf.floor_number
            ).order_by('id')
        )
        tf.hotspots.all().delete()
        new_rows = []
        used_ids = set()

        for h in src_hotspots:
            mapped_apt = None
            if h.apartment_id and h.apartment_id in src_rank_by_pk:
                rank = src_rank_by_pk[h.apartment_id]
                if rank < len(target_apts):
                    cand = target_apts[rank]
                    if cand.pk not in used_ids:
                        mapped_apt = cand
                        used_ids.add(cand.pk)
            if mapped_apt is None and h.apartment_id:
                src_area = h.apartment.total_area
                for cand in target_apts:
                    if cand.pk not in used_ids and cand.total_area == src_area:
                        mapped_apt = cand
                        used_ids.add(cand.pk)
                        break

            new_rows.append(
                ApartmentHotspot(
                    floor_explorer=tf,
                    apartment=mapped_apt,
                    polygon_points=h.polygon_points,
                    label_x=h.label_x,
                    label_y=h.label_y,
                    detected_label=f'Copied #{mapped_apt.apartment_number}' if mapped_apt else h.detected_label,
                )
            )
        ApartmentHotspot.objects.bulk_create(new_rows)
        updated_count += 1
    return updated_count

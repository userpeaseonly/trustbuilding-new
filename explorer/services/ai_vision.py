import base64
import json
import logging
import os
import re

import cv2
import httpx
import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)


def get_ai_provider_status() -> dict:
    """Return non-secret availability flags for Gemini and DeepSeek."""
    gemini_key = (getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
    ds_enabled = getattr(settings, 'AI_ENABLED', False)
    ds_key = (getattr(settings, 'AI_API_KEY', '') or '').strip()
    return {
        'gemini_ready': bool(gemini_key),
        'gemini_model': getattr(settings, 'GEMINI_MODEL', 'gemini-3.8-flash'),
        'gemini_pro_model': getattr(settings, 'GEMINI_PRO_MODEL', 'gemini-4-argon'),
        'gemini_image_model': getattr(settings, 'GEMINI_IMAGE_MODEL', 'gemini-3.1-flash-image'),
        'deepseek_ready': bool(ds_enabled and ds_key),
        'deepseek_model': os.getenv('AI_VISION_MODEL') or getattr(settings, 'AI_MODEL', 'deepseek-flash'),
        'deepseek_reasoning_model': getattr(settings, 'AI_REASONING_MODEL', 'deepseek-reasoner'),
    }


def _get_deepseek_config():
    enabled = getattr(settings, 'AI_ENABLED', False)
    api_key = (getattr(settings, 'AI_API_KEY', '') or '').strip()
    base_url = getattr(settings, 'AI_BASE_URL', 'https://api.deepseek.com') or 'https://api.deepseek.com'
    model = os.getenv('AI_VISION_MODEL') or getattr(settings, 'AI_MODEL', 'deepseek-flash') or 'deepseek-flash'
    reasoning_model = getattr(settings, 'AI_REASONING_MODEL', '') or model
    timeout = getattr(settings, 'AI_TIMEOUT_SECONDS', 30)
    return enabled, api_key, base_url, model, reasoning_model, timeout


def _get_gemini_config():
    api_key = (getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
    flash_model = getattr(settings, 'GEMINI_MODEL', 'gemini-3.8-flash') or 'gemini-3.8-flash'
    pro_model = getattr(settings, 'GEMINI_PRO_MODEL', 'gemini-4-argon') or 'gemini-4-argon'
    timeout = max(90, int(getattr(settings, 'GEMINI_TIMEOUT_SECONDS', 120)))
    return api_key, flash_model, pro_model, timeout


def _get_gemini_image_config():
    api_key = (getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
    img_model = getattr(settings, 'GEMINI_IMAGE_MODEL', 'gemini-3.1-flash-image') or 'gemini-3.1-flash-image'
    timeout = max(90, int(getattr(settings, 'GEMINI_TIMEOUT_SECONDS', 120)))
    return api_key, img_model, timeout


def generate_atmosphere_render_with_ai(hero_bytes: bytes, mode: str) -> bytes | None:
    """
    Transform a daylight exterior architectural render into photorealistic Golden-Hour Sunset or
    Blue-Hour Night lighting using Gemini native image editing (`gemini-3.1-flash-image` / preview fallback),
    preserving exact pixel framing, camera geometry, and original dimensions so interactive floor bands align.
    """
    if not hero_bytes or mode not in ('sunset', 'night'):
        return None
    api_key, primary_model, timeout = _get_gemini_image_config()
    if not api_key:
        return None

    arr = np.frombuffer(hero_bytes, dtype=np.uint8)
    orig_img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if orig_img is None:
        return None
    h0, w0 = orig_img.shape[:2]

    in_bytes, mime = _compress_image_for_api(hero_bytes, max_dim=1920, use_jpeg=True)
    if mode == 'sunset':
        prompt = (
            "Relight this exact architectural photograph/render to GOLDEN HOUR SUNSET lighting. "
            "CRITICAL CAMERA & PIXEL LOCK: Do NOT zoom out, zoom in, pan, tilt, extend boundaries, or invent extra sky/horizon above trees. "
            "Every single roof edge, window corner, tree trunk, road line, and car must remain at its EXACT identical (x, y) pixel location. "
            "ONLY change lighting & color atmosphere in-place: warm golden-amber late-afternoon grazing sunlight casting soft warm highlights "
            "across facade stonework, golden sunset haze/sky ONLY inside already-visible sky areas (if no sky is visible, bathe tree canopy in golden sunlight), "
            "subtle warm tungsten light beginning to glow inside half of the apartment windows, and soft warm bollard path lights turning on. "
            "Photorealistic architectural photography, ultra-sharp, zero geometry movement."
        )
    else:
        prompt = (
            "Relight this exact architectural photograph/render to REALISTIC BLUE-HOUR NIGHTTIME architectural photography. "
            "CRITICAL CAMERA & PIXEL LOCK: Do NOT zoom out, zoom in, pan, tilt, extend boundaries, or alter FOV. "
            "Every single roof edge, window corner, tree trunk, road line, and parked car must remain at its EXACT identical (x, y) pixel location. "
            "ONLY change lighting & atmosphere in-place: deep cobalt-navy dusk sky inside visible sky areas, cozy warm 2700K interior room lights "
            "glowing naturally through ~65% of glass apartment windows behind real mullions and curtains, subtle warm architectural facade uplights "
            "grazing vertical pilasters and lobby entrances, and warm streetlamp and garden bollard pools of light on walkways and trees. "
            "Photorealistic luxury real-estate night render, ultra-sharp, zero geometry movement."
        )

    candidates_models = [primary_model]
    for fb in ('gemini-3.1-flash-image-preview', 'gemini-2.5-flash-image'):
        if fb not in candidates_models:
            candidates_models.append(fb)

    for mdl in candidates_models:
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent'
        body = {
            'contents': [{
                'role': 'user',
                'parts': [
                    {'text': prompt},
                    {'inlineData': {'mimeType': mime, 'data': base64.b64encode(in_bytes).decode('ascii')}},
                ],
            }],
            'generationConfig': {
                'responseModalities': ['IMAGE'],
                'temperature': 0.25,
            },
        }
        try:
            resp = httpx.post(
                url,
                headers={'Content-Type': 'application/json', 'x-goog-api-key': api_key},
                json=body,
                timeout=timeout,
            )
            if resp.status_code != 200:
                logger.warning("Gemini image API %s HTTP %s: %s", mdl, resp.status_code, resp.text[:250])
                continue
            cands = resp.json().get('candidates') or []
            if not cands:
                continue
            parts = (cands[0].get('content') or {}).get('parts') or []
            for p in parts:
                inline = p.get('inlineData') if isinstance(p, dict) else None
                if inline and inline.get('data'):
                    gen_raw = base64.b64decode(inline['data'])
                    gen_img = cv2.imdecode(np.frombuffer(gen_raw, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if gen_img is None:
                        continue
                    if gen_img.shape[:2] != (h0, w0):
                        gen_img = cv2.resize(gen_img, (w0, h0), interpolation=cv2.INTER_LANCZOS4)
                    ok, out_buf = cv2.imencode('.jpg', gen_img, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    if ok:
                        return out_buf.tobytes()
        except Exception as exc:
            logger.warning("Gemini image relighting failed on %s: %s", mdl, exc)
    return None


def _extract_json_object(raw_text: str) -> dict | None:
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    fence = re.search(r'```(?:json)?\s*(\{.*\})\s*```', cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    else:
        brace = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if brace:
            cleaned = brace.group(0)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _compress_image_for_api(raw_bytes: bytes, max_dim: int = 1280, use_jpeg: bool = True) -> tuple[bytes, str]:
    """Shrink large architectural images smoothly to cut vision token cost cleanly."""
    if not raw_bytes:
        return b'', 'image/png'
    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return raw_bytes, 'image/png'
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    if use_jpeg:
        ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if ok:
            return buf.tobytes(), 'image/jpeg'
    ok, buf = cv2.imencode('.png', img)
    return (buf.tobytes(), 'image/png') if ok else (raw_bytes, 'image/png')


def call_gemini_json(
    image_items: list[tuple[str, bytes]],
    prompt_text: str,
    *,
    use_pro: bool = False,
    thinking_budget: int | None = 0,
    thinking_level: str | None = None,
    max_tokens: int = 1800,
    max_dim: int = 1280,
) -> dict | None:
    """
    Cost-optimized multimodal call to Google Gemini API (gemini-3.8-flash default,
    optional gemini-4-argon / gemini-4-carbon escalation) with structured JSON response output.
    """
    api_key, flash_model, pro_model, timeout = _get_gemini_config()
    if not api_key:
        return None

    model = pro_model if use_pro else flash_model
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'

    parts = [{'text': prompt_text}]
    for label, raw_bytes in image_items:
        if not raw_bytes:
            continue
        comp_bytes, mime = _compress_image_for_api(raw_bytes, max_dim=max_dim, use_jpeg=True)
        if label:
            parts.append({'text': f'[{label}]'})
        parts.append({
            'inlineData': {
                'mimeType': mime,
                'data': base64.b64encode(comp_bytes).decode('ascii'),
            }
        })

    # Gemini 3/4 includes thinking tokens in maxOutputTokens; ensure plenty of headroom so JSON is never truncated
    effective_max = max(int(max_tokens), 8192) if '2.5' not in model else int(max_tokens)
    gen_cfg = {
        'temperature': 0.1,
        'maxOutputTokens': effective_max,
        'responseMimeType': 'application/json',
    }
    # Gemini 2.5 accepts numeric `thinkingBudget`; Gemini 3/4 use `thinkingLevel` ("LOW"/"MEDIUM"/"HIGH")
    if '2.5' in model:
        if thinking_budget is not None:
            gen_cfg['thinkingConfig'] = {'thinkingBudget': int(thinking_budget)}
    elif thinking_level:
        gen_cfg['thinkingConfig'] = {'thinkingLevel': str(thinking_level).upper()}
    elif thinking_budget is not None:
        lvl = 'LOW' if thinking_budget == 0 else ('MEDIUM' if thinking_budget <= 2048 else 'HIGH')
        gen_cfg['thinkingConfig'] = {'thinkingLevel': lvl}

    body = {
        'contents': [{'role': 'user', 'parts': parts}],
        'generationConfig': gen_cfg,
    }

    try:
        resp = httpx.post(
            url,
            headers={'Content-Type': 'application/json', 'x-goog-api-key': api_key},
            json=body,
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning("Gemini API HTTP %s: %s", resp.status_code, resp.text[:300])
            return None
        payload = resp.json()
        candidates = payload.get('candidates') or []
        if not candidates:
            return None
        c_parts = (candidates[0].get('content') or {}).get('parts') or []
        text_chunks = [p.get('text', '') for p in c_parts if isinstance(p, dict) and p.get('text')]
        return _extract_json_object('\n'.join(text_chunks))
    except Exception as exc:
        logger.warning("Gemini API call failed cleanly: %s", exc)
        return None


def _call_deepseek_vision_json(
    image_items: list[tuple[str, bytes]],
    prompt_text: str,
    max_tokens: int = 1200,
    *,
    use_reasoning: bool = False,
) -> dict | None:
    enabled, api_key, base_url, model, reasoning_model, timeout = _get_deepseek_config()
    if not enabled or not api_key:
        return None

    chosen_model = reasoning_model if (use_reasoning and reasoning_model) else model
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        content_blocks = [{'type': 'text', 'text': prompt_text}]
        for label, raw_bytes in image_items:
            if not raw_bytes:
                continue
            comp_bytes, mime = _compress_image_for_api(raw_bytes, max_dim=1280, use_jpeg=True)
            if label:
                content_blocks.append({'type': 'text', 'text': f'[{label}]'})
            b64 = base64.b64encode(comp_bytes).decode('ascii')
            content_blocks.append({'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}'}})

        # DeepSeek v4 models may emit internal reasoning tokens before answer; give generous completion budget
        ds_max_tokens = max(int(max_tokens), 8192) if ('v4' in chosen_model or 'reason' in chosen_model) else int(max_tokens)
        resp = client.chat.completions.create(
            model=chosen_model,
            messages=[{'role': 'user', 'content': content_blocks}],
            temperature=0.1,
            max_tokens=ds_max_tokens,
        )
        content = resp.choices[0].message.content if resp.choices else ''
        return _extract_json_object(content or '')
    except Exception as exc:
        logger.warning("DeepSeek vision call (%s) failed (falling back cleanly): %s", chosen_model, exc)
        return None


def _call_hybrid_vision(
    image_items: list[tuple[str, bytes]],
    prompt_text: str,
    *,
    prefer: str = 'gemini',
    use_pro: bool = False,
    thinking_budget: int | None = 0,
    thinking_level: str | None = None,
    max_tokens: int = 2048,
    max_dim: int = 1280,
) -> dict | None:
    """
    Complexity-aware multimodal router:
      - `prefer='gemini'` (with `use_pro=True` -> gemini-4-carbon, `use_pro=False` -> gemini-3.8-flash)
        for spatial grounding, multi-image key-map registration, and perspective facade geometry;
        automatically retries on Flash if Pro fails, then DeepSeek.
      - `prefer='deepseek'` for fast OCR / floor-plan region matching / page classification (Gemini Flash fallback).
    """
    if prefer == 'gemini':
        res = call_gemini_json(
            image_items,
            prompt_text,
            use_pro=use_pro,
            thinking_budget=thinking_budget,
            thinking_level=thinking_level,
            max_tokens=max_tokens,
            max_dim=max_dim,
        )
        if res is not None:
            return res
        if use_pro:
            res = call_gemini_json(
                image_items,
                prompt_text,
                use_pro=False,
                thinking_budget=thinking_budget,
                thinking_level=thinking_level or 'MEDIUM',
                max_tokens=max_tokens,
                max_dim=max_dim,
            )
            if res is not None:
                return res
        return _call_deepseek_vision_json(
            image_items,
            prompt_text,
            max_tokens=min(max_tokens, 1600),
            use_reasoning=use_pro,
        )

    res = _call_deepseek_vision_json(
        image_items,
        prompt_text,
        max_tokens=min(max_tokens, 1600),
        use_reasoning=use_pro,
    )
    if res is not None:
        return res
    return call_gemini_json(
        image_items,
        prompt_text,
        use_pro=False,
        thinking_budget=thinking_budget,
        thinking_level=thinking_level or 'LOW',
        max_tokens=max_tokens,
        max_dim=max_dim,
    )


def match_regions_with_ai(annotated_png_bytes: bytes, expected_apartments: list[dict]) -> dict[int, str] | None:
    """Match labeled floor plan regions [1..K] to DB apartment numbers using DeepSeek OCR + Gemini fallback."""
    if not annotated_png_bytes or not expected_apartments:
        return None

    apts_brief = json.dumps(expected_apartments, ensure_ascii=False)
    prompt = (
        "You are inspecting a high-resolution residential architectural floor plan where segmented "
        "apartment suites are labeled with dark bold tags [1], [2], [3], etc.\n"
        f"Expected apartments on this floor (ground-truth database list):\n{apts_brief}\n\n"
        "TASK:\n"
        "For EVERY numbered tag [k] visible on the floor plan, match it to the exact `apartment_number` from the JSON list.\n"
        "Use BOTH:\n"
        "1. Printed apartment number badge/circle inside that suite (if present, e.g. '№ 4', 'кв. 12', or encircled '3'), AND\n"
        "2. Suite area label (`m2` total area) and room count/layout shape inside that suite.\n"
        "Each `apartment_number` should map to at most ONE region.\n\n"
        "Respond strictly with valid JSON only in this exact schema:\n"
        '{"matches": {"1": "<apartment_number>", "2": "<apartment_number>"}}'
    )
    data = _call_hybrid_vision(
        [('Floor Plan', annotated_png_bytes)],
        prompt,
        prefer='gemini',
        thinking_level='LOW',
        max_tokens=1400,
        max_dim=1440,
    )
    if not data or not isinstance(data.get('matches'), dict):
        return None

    valid_nums = {str(a['apartment_number']) for a in expected_apartments}
    out = {}
    for k, v in data['matches'].items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        apt_num = str(v).strip()
        if apt_num in valid_nums:
            out[idx] = apt_num
    return out or None


def classify_page_with_ai(page_png_bytes: bytes, page_num: int, floor_count: int) -> dict | None:
    if not page_png_bytes:
        return None

    prompt = (
        f"Classify page {page_num} of a {floor_count}-floor residential building PDF album.\n"
        'Choose `kind` from: "cover", "masterplan", "floor_plan", "render".\n'
        'If `kind` is "floor_plan", list covered floor numbers 1..N in `floors` (e.g. [1] or [2,3,4,5]).\n'
        'If `kind` is "render", set `is_aerial` to true only if it is a top-down drone/birdseye view.\n'
        'Respond strictly with valid JSON:\n'
        '{"kind": "floor_plan", "floors": [1], "is_aerial": false}'
    )
    data = _call_hybrid_vision(
        [('PDF Page', page_png_bytes)],
        prompt,
        prefer='gemini',
        thinking_level='LOW',
        max_tokens=300,
    )
    if not data or data.get('kind') not in ('cover', 'masterplan', 'floor_plan', 'render'):
        return None
    return data


def classify_render_shot_with_ai(render_bytes: bytes) -> dict | None:
    """Classify exterior architectural render shot framing to prefer full-height tower facades over lobby closeups."""
    if not render_bytes:
        return None

    prompt = (
        "Classify this 3D architectural render of a residential building.\n"
        'Set `shot_type` to one of: "full_facade", "courtyard_wide", "aerial_complex", "closeup_detail".\n'
        'Choose "full_facade" ONLY when ALL storeys (ground to roof + sky) of the building exterior are clearly visible.\n'
        'Choose "closeup_detail" if the camera crops tightly onto 1-2 lower floors or an entrance door.\n'
        "Return strict JSON:\n"
        '{"shot_type": "full_facade", "visible_floors": 5, "has_corner_bend": false}'
    )
    data = _call_hybrid_vision(
        [('Exterior Render', render_bytes)],
        prompt,
        prefer='gemini',
        thinking_budget=0,
        max_tokens=220,
    )
    if not data or data.get('shot_type') not in ('full_facade', 'courtyard_wide', 'aerial_complex', 'closeup_detail'):
        return None
    return data


def select_best_hero_render_with_ai(
    candidate_renders: list[tuple[int, bytes]],
    *,
    block_label: str = '',
    keymap_bytes: bytes | None = None,
    genplan_bytes: bytes | None = None,
) -> dict | None:
    """
    Use multi-image comparative vision (Gemini Pro when available, Flash fallback) to choose
    the single best exterior render showing `block_label` clearly at full height without close-up cropping.
    `candidate_renders`: list of (index, png_or_jpg_bytes).
    Returns {"best_index": int, "camera_view": str, "reason": str} or None.
    """
    if not candidate_renders:
        return None

    images: list[tuple[str, bytes]] = []
    if genplan_bytes:
        images.append(('SITE MASTERPLAN (GENPLAN)', genplan_bytes))
    if keymap_bytes:
        images.append((f'RED KEY-MAP FOR {block_label or "TARGET BUILDING"}', keymap_bytes))
    valid_indices = []
    for idx, rbytes in candidate_renders[:6]:
        if rbytes:
            valid_indices.append(int(idx))
            images.append((f'CANDIDATE RENDER {idx}', rbytes))
    if not valid_indices:
        return None

    target_desc = block_label or 'this residential building block'
    prompt = (
        f"You are selecting the SINGLE BEST Hero Exterior Render for '{target_desc}' on a real-estate presentation website.\n"
        "Inspect ALL numbered CANDIDATE RENDER images alongside the SITE MASTERPLAN and RED KEY-MAP (where the target block is highlighted in red).\n\n"
        "SELECTION CRITERIA:\n"
        "1. REJECT any tight close-up crop showing only 1-2 lower floors or an entrance lobby doorway ('closeup_detail').\n"
        "2. PREFER views where the SPECIFIC TARGET BLOCK highlighted in the RED KEY-MAP (check corner L-wings vs middle street segments vs courtyard side) "
        "is clearly visible, prominent, unobstructed, and shows ALL storeys from Floor 1 ground base to top roof cornice.\n"
        "3. If one angle shows the target wing close-up in 3/4 street perspective (e.g. foreground L-wing) and another is a distant high-altitude overhead shot, "
        "prefer the clearer street/courtyard architectural perspective where the target block's floors can be hovered cleanly.\n"
        "4. However, if the target block faces INSIDE the courtyard or is hidden behind another wing in the street view, prefer the courtyard wide shot where ALL its floors are unobstructed.\n\n"
        "Respond strictly with JSON:\n"
        '{"best_index": 0, "camera_view": "street_3quarter_east", "reason": "Shows Block 1 foreground corner L-wing at full 5-storey height"}'
    )
    api_key, _fl, pro_m, _to = _get_gemini_config()
    data = _call_hybrid_vision(
        images,
        prompt,
        prefer='gemini',
        use_pro=bool(api_key and pro_m),
        thinking_level='LOW',
        max_tokens=600,
        max_dim=1024,
    )
    if not data:
        return None
    try:
        best_idx = int(data['best_index'])
    except (KeyError, TypeError, ValueError):
        return None
    if best_idx not in valid_indices:
        return None
    return {
        'best_index': best_idx,
        'camera_view': str(data.get('camera_view', '')),
        'reason': str(data.get('reason', ''))[:240],
    }


def _polygon_area_pct(pts: list[list[float]]) -> float:
    if len(pts) < 3:
        return 0.0
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def _parse_faces_from_ai_payload(
    data: dict,
    *,
    x_offset_pct: float = 0.0,
    y_offset_pct: float = 0.0,
    x_scale_pct: float = 100.0,
    y_scale_pct: float = 100.0,
) -> list[dict]:
    """
    Convert either `vertical_edges` (ordered left-to-right vertical corner lines `[top, bottom]` in 0..1000)
    or `faces` (ordered quads `{tl, tr, br, bl}` in 0..1000) into normalized 0..100% face quads.
    Supports 1, 2, 3, or more connected planar faces (0, 1, 2, or more corner bends), including steep
    foreshortened perspective side walls on L-shaped wings.
    """
    def _to_pct(pt) -> list[float]:
        px = x_offset_pct + (float(pt[0]) / 1000.0) * x_scale_pct
        py = y_offset_pct + (float(pt[1]) / 1000.0) * y_scale_pct
        return [
            round(max(0.0, min(100.0, px)), 2),
            round(max(0.0, min(100.0, py)), 2),
        ]

    faces_pct: list[dict] = []

    raw_edges = data.get('vertical_edges')
    if isinstance(raw_edges, list) and len(raw_edges) >= 2:
        parsed_edges = []
        for ed in raw_edges:
            if not isinstance(ed, dict):
                continue
            try:
                t_pt = _to_pct(ed['top'])
                b_pt = _to_pct(ed['bottom'])
                if (b_pt[1] - t_pt[1]) > 2.5:
                    parsed_edges.append({'top': t_pt, 'bottom': b_pt})
            except Exception:
                continue
        for i in range(len(parsed_edges) - 1):
            e0, e1 = parsed_edges[i], parsed_edges[i + 1]
            top_span = float(np.hypot(e1['top'][0] - e0['top'][0], e1['top'][1] - e0['top'][1]))
            bot_span = float(np.hypot(e1['bottom'][0] - e0['bottom'][0], e1['bottom'][1] - e0['bottom'][1]))
            if max(top_span, bot_span) >= 1.2:
                faces_pct.append({
                    'tl': list(e0['top']),
                    'tr': list(e1['top']),
                    'br': list(e1['bottom']),
                    'bl': list(e0['bottom']),
                })
        if faces_pct:
            return faces_pct

    raw_faces = data.get('faces')
    if not isinstance(raw_faces, list):
        return []

    for f in raw_faces:
        if not isinstance(f, dict):
            continue
        try:
            coords = {k: _to_pct(f[k]) for k in ('tl', 'tr', 'br', 'bl')}
            avg_top_y = 0.5 * (coords['tl'][1] + coords['tr'][1])
            avg_bot_y = 0.5 * (coords['bl'][1] + coords['br'][1])
            top_span = float(np.hypot(coords['tr'][0] - coords['tl'][0], coords['tr'][1] - coords['tl'][1]))
            bot_span = float(np.hypot(coords['br'][0] - coords['bl'][0], coords['br'][1] - coords['bl'][1]))
            if max(top_span, bot_span) >= 1.2 and (avg_bot_y - avg_top_y) > 2.5:
                faces_pct.append(coords)
        except Exception:
            continue

    if not faces_pct:
        return []

    faces_pct.sort(key=lambda fc: 0.5 * (fc['tl'][0] + fc['bl'][0]))
    for i in range(len(faces_pct) - 1):
        cur, nxt = faces_pct[i], faces_pct[i + 1]
        if abs(cur['tr'][0] - nxt['tl'][0]) <= 2.5 and abs(cur['br'][0] - nxt['bl'][0]) <= 2.5:
            mid_tx = round(0.5 * (cur['tr'][0] + nxt['tl'][0]), 2)
            mid_ty = round(0.5 * (cur['tr'][1] + nxt['tl'][1]), 2)
            mid_bx = round(0.5 * (cur['br'][0] + nxt['bl'][0]), 2)
            mid_by = round(0.5 * (cur['br'][1] + nxt['bl'][1]), 2)
            cur['tr'] = [mid_tx, mid_ty]
            nxt['tl'] = [mid_tx, mid_ty]
            cur['br'] = [mid_bx, mid_by]
            nxt['bl'] = [mid_bx, mid_by]

    return faces_pct


def detect_facade_and_faces_with_ai(
    render_bytes: bytes,
    floor_count: int,
    *,
    building_label: str = '',
    keymap_bytes: bytes | None = None,
    genplan_bytes: bytes | None = None,
    complex_buildings: list[dict] | None = None,
) -> dict | None:
    """
    Key-map & Genplan-guided spatial grounding using Gemini Pro (`GEMINI_PRO_MODEL`) with automatic
    Two-Stage High-Resolution Zoomed Multi-Bend Corner Refinement for complex/L-shaped blocks.

    Supports 1, 2, 3, or more connected planar facade surfaces (e.g., 2 corner bends on an L-shaped wing:
    inner concave corner + projecting side wall + outer convex corner pillar + front end wall).
    Returns {"faces": [{"tl", "tr", "br", "bl"}], "is_closeup": bool, "camera_view": str, "notes": str}
    in 0..100 percent coordinates covering ONLY the target block's storeys.
    """
    if not render_bytes or floor_count < 1:
        return None

    has_context = bool(keymap_bytes or genplan_bytes or (complex_buildings and len(complex_buildings) > 1))
    images: list[tuple[str, bytes]] = [('TARGET EXTERIOR RENDER', render_bytes)]
    if genplan_bytes:
        images.append(('SITE MASTERPLAN (GENPLAN)', genplan_bytes))
    if keymap_bytes:
        images.append((f'RED KEY-MAP FOR {building_label or "TARGET BLOCK"}', keymap_bytes))

    siblings_txt = (
        f"\nAll blocks in this development: {json.dumps(complex_buildings, ensure_ascii=False)}\n"
        if complex_buildings else ""
    )
    target_txt = building_label or f"this {floor_count}-storey building"

    if has_context:
        prompt = (
            f"You are an expert architectural CAD/3D visual mapper isolating ONLY the target building block '{target_txt}' "
            f"({floor_count} storeys) inside the TARGET EXTERIOR RENDER.\n"
            f"{siblings_txt}\n"
            "HOW TO READ THE REFERENCE IMAGES:\n"
            "- RED KEY-MAP (`Схема блокировки`) highlights '{target_txt}' in BRIGHT RED within the overall complex outline, and greys out sibling blocks.\n"
            "- SITE MASTERPLAN (`Ген план`) shows the numbered blocks and street/courtyard geometry.\n"
            "- CRITICAL CAMERA CHECK: First identify where the camera is standing in TARGET EXTERIOR RENDER relative to the Genplan & Red Key-Map:\n"
            "  * If looking from the South street toward the front elevation, Red Key-Map LEFT = Image LEFT and Red Key-Map RIGHT = Image RIGHT.\n"
            "  * If looking from the North courtyard back toward the U-shaped building (or oblique courtyard view), LEFT and RIGHT SWAP horizontally relative to the south-facing Red Key-Map!\n"
            "  * If separate 2-storey townhouses/cottages appear in the scene, NEVER include them inside the multi-storey block.\n\n"
            "BOUNDING & MULTI-BEND CORNER RULES (0..1000 normalized coords on TARGET EXTERIOR RENDER):\n"
            f"1. Isolate STRICTLY the exterior facade section belonging to '{target_txt}' — do NOT span adjacent sibling blocks!\n"
            f"2. Vertically trace ONLY the {floor_count} residential storeys: from bottom of Floor 1 (at ground/plinth level) up to the top cornice of Floor {floor_count} (BELOW roof solar panels and roof parapet).\n"
            "3. CHECK FOR MULTIPLE CORNER BENDS (1, 2, or 3+ planar faces):\n"
            "   - A straight flat block has 1 face (0 bends, 2 vertical edges).\n"
            "   - An exterior corner block seen from outside has 2 faces (1 bend at the outer corner, 3 vertical edges).\n"
            "   - An L-shaped wing projecting toward the camera (such as a courtyard L-arm!) has 3 VISIBLE FACES and 2 CORNER BENDS (4 vertical edges left-to-right):\n"
            "     * Face 1: the main rear courtyard wall up to the INNER 90-degree concave corner (Bend 1).\n"
            "     * Face 2: the steep foreshortened side wall of the projecting L-wing running forward/downward from Bend 1 (inner concave corner) to Bend 2 (the outer white corner pillar)!\n"
            "     * Face 3: the front-facing end wall of the projecting L-wing running from Bend 2 (outer corner pillar) to the far-right outer edge, where floors run nearly horizontally!\n"
            "    NEVER skip Face 2 by drawing a single diagonal from the inner concave corner directly to the far-right outer edge — always bend at BOTH the inner concave corner AND the outer convex corner pillar!\n\n"
            "Respond strictly with JSON containing BOTH `vertical_edges` (left-to-right vertical corner/seam lines from Floor 5 top to Floor 1 bottom) and `faces`:\n"
            "{\n"
            '  "camera_view": "courtyard_north_to_south",\n'
            '  "target_location_notes": "Right L-wing with 3 visible planar faces and 2 corner bends (inner concave corner + outer convex corner pillar)",\n'
            '  "vertical_edges": [\n'
            '    {"role": "left_seam", "top": [715, 178], "bottom": [710, 308]},\n'
            '    {"role": "inner_concave_corner", "top": [795, 180], "bottom": [775, 312]},\n'
            '    {"role": "outer_convex_corner", "top": [832, 272], "bottom": [792, 408]},\n'
            '    {"role": "right_outer_edge", "top": [925, 292], "bottom": [888, 422]}\n'
            "  ],\n"
            '  "faces": [\n'
            '    {"tl": [715, 178], "tr": [795, 180], "br": [775, 312], "bl": [710, 308]},\n'
            '    {"tl": [795, 180], "tr": [832, 272], "br": [792, 408], "bl": [775, 312]},\n'
            '    {"tl": [832, 272], "tr": [925, 292], "br": [888, 422], "bl": [792, 408]}\n'
            "  ],\n"
            '  "is_closeup": false\n'
            "}"
        )
    else:
        prompt = (
            f"You are analyzing an exterior architectural 3D render of a {floor_count}-storey residential building"
            f"{' (' + target_txt + ')' if building_label else ''}.\n"
            f"Locate ONLY the visible residential storeys on the target building (from bottom of Floor 1 to the top cornice under the roof of Floor {floor_count}; ignore sky, solar roof panels, trees in front, and parking/cars below).\n"
            "Use normalized 0..1000 coordinates where (0,0) is top-left and (1000,1000) is bottom-right.\n"
            "If the building turns 1 or 2+ vertical architectural corners in perspective (e.g., an outer corner or an L-wing with an inner concave corner + foreshortened side wall + outer convex corner pillar), split left-to-right at EVERY vertical corner edge into 2, 3, or more corner-connected `faces`.\n"
            "Return strict JSON:\n"
            "{\n"
            '  "camera_view": "street_front",\n'
            '  "target_location_notes": "Single standalone facade",\n'
            '  "faces": [\n'
            '    {"tl": [100, 280], "tr": [890, 280], "br": [890, 740], "bl": [100, 740]}\n'
            "  ],\n"
            '  "is_closeup": false\n'
            "}"
        )

    api_key, _fl, pro_m, _to = _get_gemini_config()
    use_pro_model = bool(has_context and api_key and pro_m)
    data = _call_hybrid_vision(
        images,
        prompt,
        prefer='gemini',
        use_pro=use_pro_model,
        thinking_level='MEDIUM' if has_context else 'LOW',
        max_tokens=2048,
        max_dim=1280,
    )
    if not data:
        return None

    faces_pct = _parse_faces_from_ai_payload(data)
    if not faces_pct:
        return None

    # Stage 2: High-Resolution Cropped Zoom Multi-Bend Refinement when target block is a sub-region of a wide scene
    try:
        arr = np.frombuffer(render_bytes, dtype=np.uint8)
        full_img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if full_img is not None and float(np.std(full_img)) > 8.0:
            fh, fw = full_img.shape[:2]
            all_x = [p[0] for fc in faces_pct for p in (fc['tl'], fc['tr'], fc['br'], fc['bl'])]
            all_y = [p[1] for fc in faces_pct for p in (fc['tl'], fc['tr'], fc['br'], fc['bl'])]
            span_w = max(all_x) - min(all_x)
            if has_context and (span_w < 60.0 or len(faces_pct) >= 2):
                pad_x = max(5.0, span_w * 0.22)
                pad_y = max(6.0, (max(all_y) - min(all_y)) * 0.28)
                x1p = max(0.0, min(all_x) - pad_x)
                x2p = min(100.0, max(all_x) + pad_x)
                y1p = max(0.0, min(all_y) - pad_y)
                y2p = min(100.0, max(all_y) + pad_y)
                cx1, cx2 = int(round(x1p / 100.0 * fw)), int(round(x2p / 100.0 * fw))
                cy1, cy2 = int(round(y1p / 100.0 * fh)), int(round(y2p / 100.0 * fh))
                if (cx2 - cx1) >= 160 and (cy2 - cy1) >= 120:
                    crop_bgr = full_img[cy1:cy2, cx1:cx2]
                    ok_c, crop_buf = cv2.imencode('.png', crop_bgr)
                    if ok_c:
                        zoom_imgs: list[tuple[str, bytes]] = [('ZOOMED TARGET BLOCK CROP', crop_buf.tobytes())]
                        if keymap_bytes:
                            zoom_imgs.append((f'RED KEY-MAP FOR {target_txt}', keymap_bytes))
                        zoom_prompt = (
                            f"You are inspecting a HIGH-RESOLUTION ZOOMED CROP of '{target_txt}' ({floor_count} storeys, highlighted in red on the RED KEY-MAP).\n"
                            "Your job is to refine the exact left-to-right vertical corner edges (`vertical_edges`) of ONLY this target block in [0..1000] crop coordinates so that every floor band bends accurately around every architectural corner!\n\n"
                            "CRITICAL MULTI-BEND CHECK:\n"
                            "1. Count every visible planar facade face on this target block from left to right:\n"
                            "   - If the block is a straight flat segment (no corner turn inside this block), output 2 vertical edges (1 face, 0 bends).\n"
                            "   - If the block turns 1 visible corner (e.g. front elevation + side return elevation), output 3 vertical edges (2 faces, 1 bend).\n"
                            "   - If the block is an L-shaped wing where you see:\n"
                            "     (a) a rear courtyard facade section facing the viewer,\n"
                            "     (b) an INNER 90-degree CONCAVE CORNER (Bend 1) where the projecting wing turns forward toward the camera along a steep foreshortened side wall with balconies, AND\n"
                            "     (c) an OUTER 90-degree CONVEX CORNER PILLAR (Bend 2) where the steep side wall meets the front-facing 3-window end facade of the projecting wing,\n"
                            "     you MUST output 4 vertical edges (3 faces, 2 bends: Edge 0=left seam with neighbor block, Edge 1=inner concave corner, Edge 2=outer convex corner pillar, Edge 3=far-right outer edge)!\n"
                            f"2. At EVERY vertical edge, place `top` at the exact top of Floor {floor_count}'s windows/cornice (BELOW roof parapet/solar panels) and `bottom` at the exact base of Floor 1's windows/plinth at ground level, so slicing {floor_count} equal floors between `bottom` and `top` aligns horizontally with the {floor_count} window rows on EVERY face!\n\n"
                            "Return strict JSON:\n"
                            "{\n"
                            '  "vertical_edges": [\n'
                            '    {"role": "left_edge", "top": [x, y], "bottom": [x, y]},\n'
                            '    {"role": "corner_or_right_edge", "top": [x, y], "bottom": [x, y]}\n'
                            "  ]\n"
                            "}"
                        )
                        zoom_data = call_gemini_json(
                            zoom_imgs,
                            zoom_prompt,
                            use_pro=use_pro_model,
                            thinking_level='HIGH',
                            max_tokens=2048,
                            max_dim=1440,
                        )
                        if zoom_data:
                            refined = _parse_faces_from_ai_payload(
                                zoom_data,
                                x_offset_pct=x1p,
                                y_offset_pct=y1p,
                                x_scale_pct=(x2p - x1p),
                                y_scale_pct=(y2p - y1p),
                            )
                            if refined:
                                faces_pct = refined
    except Exception as exc:
        logger.debug("Zoomed multi-bend refinement skipped cleanly: %s", exc)

    return {
        'faces': faces_pct,
        'is_closeup': bool(data.get('is_closeup', False)),
        'camera_view': str(data.get('camera_view', '')),
        'notes': str(data.get('target_location_notes', ''))[:240],
    }


def estimate_facade_bounds_with_ai(render_png_bytes: bytes, floor_count: int) -> dict[str, float] | None:
    """Backward-compatible wrapper returning overall bounding box from multi-face AI detection."""
    res = detect_facade_and_faces_with_ai(render_png_bytes, floor_count)
    if not res or not res.get('faces'):
        return None
    faces = res['faces']
    xl = min(min(f['tl'][0], f['bl'][0]) for f in faces)
    xr = max(max(f['tr'][0], f['br'][0]) for f in faces)
    yt = min(min(f['tl'][1], f['tr'][1]) for f in faces)
    yb = max(max(f['bl'][1], f['br'][1]) for f in faces)
    if (xr - xl) >= 12.0 and (yb - yt) >= 8.0:
        return {'x_left': round(xl, 2), 'x_right': round(xr, 2), 'y_top': round(yt, 2), 'y_bottom': round(yb, 2)}
    return None


def extract_compass_with_ai(genplan_bytes: bytes) -> float | None:
    """Read True North arrow orientation (degrees clockwise from image UP) from a Genplan/Site Plan."""
    if not genplan_bytes:
        return None

    prompt = (
        "Inspect the North compass arrow (labeled 'С', 'N', or North pointer) on this architectural site masterplan.\n"
        "Report `compass_angle` in degrees [0..359] clockwise from screen UP (0=North points straight up, 90=right, 180=down, 270=left, 315=up-left).\n"
        "Return strict JSON:\n"
        '{"compass_angle": 325.0, "confidence": 0.9}'
    )
    data = _call_hybrid_vision(
        [('Site Masterplan Compass', genplan_bytes)],
        prompt,
        prefer='gemini',
        thinking_budget=0,
        max_tokens=160,
    )
    if not data:
        return None
    try:
        ang = float(data['compass_angle']) % 360.0
        return round(ang, 1)
    except (KeyError, TypeError, ValueError):
        return None


def match_complex_blocks_with_ai(
    aerial_bytes: bytes,
    buildings_meta: list[dict],
    *,
    genplan_bytes: bytes | None = None,
    keymap_images: list[tuple[int, str, bytes]] | None = None,
) -> list[dict] | None:
    """
    Multi-image cross-registration between an Aerial 3D complex render, an optional Genplan,
    and optional per-block red `Схема блокировки` key-maps.

    Returns list of dicts:
      [{"building_id": int, "polygon_points": [[x_pct, y_pct], ...], "label_x": float, "label_y": float,
        "confidence": float, "notes": str}]
    """
    if not aerial_bytes or not buildings_meta:
        return None

    images = [('AERIAL COMPLEX RENDER', aerial_bytes)]
    if genplan_bytes:
        images.append(('SITE MASTERPLAN (GENPLAN)', genplan_bytes))
    for _bid, b_label, km_bytes in (keymap_images or []):
        if km_bytes:
            images.append((f'RED KEY-MAP FOR {b_label}', km_bytes))

    bld_json = json.dumps(buildings_meta, ensure_ascii=False)
    prompt = (
        "You are an expert architectural spatial matcher for residential real-estate developments.\n"
        "Look carefully at the AERIAL COMPLEX RENDER, the SITE MASTERPLAN (if provided), and any RED KEY-MAP thumbnails (which highlight one specific block in bright red).\n\n"
        f"Target project buildings to locate on the AERIAL COMPLEX RENDER:\n{bld_json}\n\n"
        "STRICT RULES:\n"
        "1. First verify the camera orientation between AERIAL COMPLEX RENDER and SITE MASTERPLAN (check where the parking street vs courtyard garden vs adjacent 2-storey townhouses lie — the aerial camera may be rotated relative to the Genplan!).\n"
        "2. Match EVERY target building accurately using building shape (L-wing vs straight wing), block order around the courtyard/street, and RED KEY-MAP geometry (`Схема блокировки`).\n"
        "3. IGNORE existing neighbor/non-project buildings and 2-storey cottages/townhouses (such as marked 'Существующие здания' or low-rise villa rows) unless explicitly listed in target buildings.\n"
        "4. Return polygon coordinates normalized to [0..1000] where (0,0) is top-left and (1000,1000) is bottom-right of AERIAL COMPLEX RENDER. Polygons for different blocks MUST NOT overlap substantially.\n"
        "5. Trace tight 4-8 point roof+facade polygons covering each matched building block.\n"
        "6. Provide an honest `confidence` (0.0 to 1.0) and a concise architectural `notes` explanation.\n\n"
        "Respond with strict JSON only:\n"
        "{\n"
        '  "blocks": [\n'
        '    {\n'
        '      "building_id": 2,\n'
        '      "polygon_1000": [[700, 560], [860, 560], [860, 770], [700, 770]],\n'
        '      "label_1000": [780, 670],\n'
        '      "confidence": 0.96,\n'
        '      "notes": "Right L-wing matching Block 1 red key-map"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    api_key, _fl, pro_m, _to = _get_gemini_config()
    data = _call_hybrid_vision(
        images,
        prompt,
        prefer='gemini',
        use_pro=bool(api_key and pro_m),
        thinking_level='MEDIUM',
        max_tokens=2800,
        max_dim=1440,
    )
    if not data or not isinstance(data.get('blocks'), list):
        return None

    valid_ids = {int(b['id']) for b in buildings_meta if 'id' in b}
    results = []
    seen = set()
    for row in data['blocks']:
        if not isinstance(row, dict):
            continue
        try:
            bid = int(row['building_id'])
        except (KeyError, TypeError, ValueError):
            continue
        if bid not in valid_ids or bid in seen:
            continue
        raw_poly = row.get('polygon_1000') or []
        if not isinstance(raw_poly, list) or len(raw_poly) < 3:
            continue
        poly_pct = []
        valid_pts = True
        for pt in raw_poly:
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                valid_pts = False
                break
            x = round(max(0.0, min(100.0, float(pt[0]) / 10.0)), 2)
            y = round(max(0.0, min(100.0, float(pt[1]) / 10.0)), 2)
            poly_pct.append([x, y])
        if not valid_pts or len(poly_pct) < 3:
            continue

        lbl = row.get('label_1000')
        if isinstance(lbl, (list, tuple)) and len(lbl) == 2:
            lx = round(max(0.0, min(100.0, float(lbl[0]) / 10.0)), 2)
            ly = round(max(0.0, min(100.0, float(lbl[1]) / 10.0)), 2)
        else:
            lx = round(sum(p[0] for p in poly_pct) / len(poly_pct), 2)
            ly = round(sum(p[1] for p in poly_pct) / len(poly_pct), 2)

        conf = row.get('confidence', 0.85)
        try:
            conf = round(max(0.0, min(1.0, float(conf))), 2)
        except (TypeError, ValueError):
            conf = 0.85

        seen.add(bid)
        results.append({
            'building_id': bid,
            'polygon_points': poly_pct,
            'label_x': lx,
            'label_y': ly,
            'confidence': conf,
            'notes': str(row.get('notes', ''))[:240],
        })
    return results or None

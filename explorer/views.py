import json
import os
import re
import subprocess
import tempfile
import uuid

import cv2
import numpy as np
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from building.models import Apartment, Building
from building.views import get_user_company
from explorer.forms import ComplexExplorerForm
from explorer.models import (
    ApartmentHotspot,
    BuildingExplorer,
    ComplexBuildingHotspot,
    ComplexExplorer,
    FloorExplorer,
)
from explorer.services import ai_vision
from explorer.services.extraction import (
    apply_floor_plan_extraction,
    auto_detect_facade_bands,
    auto_detect_facade_bands_and_faces,
    copy_floor_layout_to_targets,
    decode_image_bytes,
    extract_building_from_pdf,
    slice_facade_into_floors,
)
from explorer.services.spatial_matcher import (
    analyze_view_overlay,
    auto_analyze_building_facade,
    auto_detect_complex_blocks,
    extract_facade_windows_and_canopy,
    generate_building_atmosphere_renders,
)
from users.permissions import get_safe_redirect_for_user, has_permission, require_permission


_FILE_HASH_CACHE: dict[tuple[str, int], str] = {}


def _storage_file_sha1(rel_path: str) -> str:
    """Content hash of a stored file (cached per path+size) to spot byte-identical renders."""
    if not rel_path:
        return ''
    try:
        size = default_storage.size(rel_path)
        key = (rel_path, size)
        if key not in _FILE_HASH_CACHE:
            import hashlib
            h = hashlib.sha1()
            with default_storage.open(rel_path, 'rb') as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b''):
                    h.update(chunk)
            _FILE_HASH_CACHE[key] = h.hexdigest()
        return _FILE_HASH_CACHE[key]
    except Exception:
        return ''


def _reject_pure_customer(user):
    if getattr(user, 'is_customer', False) and not (user.is_company or getattr(user, 'is_staff_member', False)):
        raise Http404("Not found")


def _require_any_view_permission(request):
    _reject_pure_customer(request.user)
    if has_permission(request.user, 'view_buildings') or has_permission(request.user, 'view_contracts'):
        return None
    messages.error(request, _("You don't have permission to perform this action."))
    fallback = get_safe_redirect_for_user(request.user)
    return redirect(fallback) if fallback else HttpResponseForbidden("Permission denied.")


def _safe_storage_url(rel_path: str) -> str:
    if not rel_path:
        return ''
    try:
        return default_storage.url(rel_path)
    except Exception:
        return ''


def _collect_company_render_library(company) -> list[dict]:
    """Gather all extracted renders & masterplans across the company's BuildingExplorers."""
    items = []
    explorers = BuildingExplorer.objects.filter(building__company=company).select_related('building')
    for exp in explorers:
        b_label = f"{exp.building.name}" + (f" ({_('Block')} {exp.building.block_number})" if exp.building.block_number else '')
        for r in (exp.extra_renders or []):
            rel_path = r.get('path')
            if rel_path and default_storage.exists(rel_path):
                items.append({
                    'building_name': b_label,
                    'path': rel_path,
                    'url': _safe_storage_url(rel_path),
                    'label': r.get('label', 'Render'),
                    'width': int(r.get('width', 1600)),
                    'height': int(r.get('height', 1000)),
                })
    return items


def _format_short_buyer_name(full_name: str) -> str:
    """Format 'Ботиров Шербек Ойбек ўғли' -> 'Ботиров Ш.' for compact floor-plan badges."""
    parts = [p for p in (full_name or '').strip().split() if p]
    if not parts:
        return ''
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0]}."


def serialize_building_payload(
    building_explorer: BuildingExplorer,
    *,
    include_crm_actions: bool = False,
    can_create_contracts: bool = False,
    complex_back_url: str = '',
    complex_name: str = '',
) -> dict:
    """
    Build frontend payload for presentation.html.
    Includes buyer_name on SOLD/RESERVED units while never exposing phone numbers, passport data, or prices.
    """
    building = building_explorer.building
    apts = list(
        building.apartments.filter(is_real=True)
        .prefetch_related('contracts__customer', 'contracts__payment_logs')
        .order_by('floor_number', 'entrance_number', 'id')
    )

    create_base = reverse('contract:create') if (include_crm_actions and can_create_contracts) else ''

    apt_list = []
    apt_by_id = {}
    floor_stats: dict[int, dict[str, int]] = {
        fl: {'total': 0, 'available': 0, 'reserved': 0, 'sold': 0}
        for fl in range(1, building.floor_count + 1)
    }

    for apt in apts:
        fl_stat = floor_stats.setdefault(apt.floor_number, {'total': 0, 'available': 0, 'reserved': 0, 'sold': 0})
        fl_stat['total'] += 1
        if apt.status == Apartment.STATUS_AVAILABLE:
            fl_stat['available'] += 1
        elif apt.status == Apartment.STATUS_RESERVED:
            fl_stat['reserved'] += 1
        elif apt.status == Apartment.STATUS_SOLD:
            fl_stat['sold'] += 1

        buyer_name = ''
        paid_percentage = 0.0
        if apt.status in (Apartment.STATUS_SOLD, Apartment.STATUS_RESERVED):
            contracts = list(apt.contracts.all())
            active_c = next((c for c in contracts if c.status in ('ACTIVE', 'COMPLETED') and c.customer_id), None)
            if not active_c:
                active_c = next((c for c in contracts if c.customer_id), None)
            if active_c:
                if active_c.customer:
                    buyer_name = (active_c.customer.full_name or '').strip()
                total_amt = float(active_c.total_amount or 0)
                if total_amt > 0:
                    paid_sum = sum(float(p.amount or 0) for p in active_c.payment_logs.all())
                    paid_percentage = round(min(100.0, max(0.0, (paid_sum / total_amt) * 100.0)), 1)

        item = {
            'id': apt.pk,
            'apartment_number': str(apt.apartment_number),
            'floor_number': apt.floor_number,
            'entrance_number': apt.entrance_number,
            'living_room_count': apt.living_room_count,
            'total_area': str(apt.total_area),
            'living_area': str(apt.living_area),
            'balcony_area': str(apt.balcony_area),
            'status': apt.status,
            'status_label': str(apt.get_status_display()),
            'buyer_name': buyer_name,
            'buyer_short': _format_short_buyer_name(buyer_name),
            'paid_percentage': paid_percentage,
        }
        if create_base and apt.status == Apartment.STATUS_AVAILABLE:
            item['create_contract_url'] = f"{create_base}?apartment={apt.pk}"
        apt_list.append(item)
        apt_by_id[apt.pk] = item

    floors_qs = building_explorer.floors.prefetch_related('hotspots').order_by('floor_number')
    floors_data = []
    for fe in floors_qs:
        hotspots = []
        for hs in fe.hotspots.all():
            if not hs.polygon_points or len(hs.polygon_points) < 3:
                continue
            hotspots.append({
                'id': hs.pk,
                'apartment_id': hs.apartment_id,
                'polygon_points': hs.polygon_points,
                'label_x': hs.label_x,
                'label_y': hs.label_y,
                'detected_label': hs.detected_label,
            })

        fl_stat = floor_stats.get(fe.floor_number, {'total': 0, 'available': 0, 'reserved': 0, 'sold': 0})
        plan_url = ''
        if fe.plan_image:
            ver = int(building_explorer.updated_at.timestamp()) if building_explorer.updated_at else 1
            plan_url = f"{fe.plan_image.url}?v={ver}"
        floors_data.append({
            'floor_number': fe.floor_number,
            'facade_polygon': fe.facade_polygon or [],
            'plan_image_url': plan_url,
            'plan_width': fe.plan_width or 1600,
            'plan_height': fe.plan_height or 1000,
            'stats': fl_stat,
            'hotspots': hotspots,
            'apartments': [a for a in apt_list if a['floor_number'] == fe.floor_number],
        })

    extra_renders = []
    hero_sha = _storage_file_sha1(building_explorer.hero_render.name) if building_explorer.hero_render else ''
    view_overlays = building_explorer.view_overlays or {}
    for er in (building_explorer.extra_renders or []):
        if er.get('sky_score', 0) < 0:
            continue
        er_path = er.get('path', '')
        url = _safe_storage_url(er_path)
        if not url:
            continue
        # Skip angles that are byte-identical to the Main render (same picture shown twice).
        if hero_sha and _storage_file_sha1(er_path) == hero_sha:
            continue
        clean_lbl = re.sub(r'\s*\(p\.\d+\)', '', str(er.get('label', 'Angle'))).strip() or 'Angle'
        floors_map = {}
        for fk, poly in ((view_overlays.get(er_path) or {}).get('floors') or {}).items():
            valid = _valid_polygon(poly)
            if valid:
                floors_map[str(fk)] = valid
        extra_renders.append({
            'label': clean_lbl,
            'url': url,
            'width': er.get('width', 1600),
            'height': er.get('height', 1000),
            # Floor bands calibrated for THIS camera angle. Empty -> floors are not clickable on the image.
            'floors': floors_map,
        })

    summary = {
        'total': sum(s['total'] for s in floor_stats.values()),
        'available': sum(s['available'] for s in floor_stats.values()),
        'reserved': sum(s['reserved'] for s in floor_stats.values()),
        'sold': sum(s['sold'] for s in floor_stats.values()),
    }

    ai_meta = building_explorer.ai_metadata or {}
    canopy_url = _safe_storage_url(ai_meta.get('canopy_path', ''))
    sunset_render_url = _safe_storage_url(ai_meta.get('sunset_hero_path', ''))
    night_render_url = _safe_storage_url(ai_meta.get('night_hero_path', ''))

    return {
        'mode': 'building',
        'is_crm': bool(include_crm_actions),
        'building': {
            'id': building.pk,
            'name': building.name,
            'block_number': building.block_number,
            'address': building.address,
            'delivery_quarter': building.delivery_quarter,
            'floor_count': building.floor_count,
            'entrance_count': building.entrance_count,
            'hero_render_url': building_explorer.hero_render.url if building_explorer.hero_render else '',
            'sunset_render_url': sunset_render_url,
            'night_render_url': night_render_url,
            'hero_width': building_explorer.hero_width or 1600,
            'hero_height': building_explorer.hero_height or 1000,
            'extra_renders': extra_renders,
            'facade_faces': building_explorer.facade_faces or [],
            'canopy_url': canopy_url,
            'windows_by_floor': ai_meta.get('windows_by_floor') or {},
            'compass_angle': float(building_explorer.compass_angle or 0.0),
            'atmosphere_enabled': building_explorer.atmosphere_enabled,
            'summary': summary,
        },
        'complex_back_url': complex_back_url,
        'complex_name': complex_name,
        'floors': floors_data,
        'apartments': apt_by_id,
    }


def serialize_complex_payload(
    complex_obj: ComplexExplorer,
    *,
    include_crm_actions: bool = False,
    public_token: str = '',
    fullscreen: bool = False,
) -> dict:
    """
    Build frontend payload for complex masterplan view.
    """
    hotspots = []
    total_all = avail_all = sold_all = res_all = 0

    hs_qs = complex_obj.building_hotspots.select_related('building').order_by('building__block_number', 'building__id')
    for hs in hs_qs:
        b = hs.building
        counts = b.apartments.filter(is_real=True).aggregate(
            total=Count('id'),
            available=Count('id', filter=Q(status=Apartment.STATUS_AVAILABLE)),
            reserved=Count('id', filter=Q(status=Apartment.STATUS_RESERVED)),
            sold=Count('id', filter=Q(status=Apartment.STATUS_SOLD)),
        )
        t_cnt = counts['total'] or 0
        a_cnt = counts['available'] or 0
        r_cnt = counts['reserved'] or 0
        s_cnt = counts['sold'] or 0
        total_all += t_cnt
        avail_all += a_cnt
        res_all += r_cnt
        sold_all += s_cnt

        exp = BuildingExplorer.objects.filter(building=b).first()
        target_url = ''
        if include_crm_actions:
            fs_q = '&fullscreen=1' if fullscreen else ''
            target_url = f"{reverse('explorer:building_view', args=[b.pk])}?complex={complex_obj.pk}{fs_q}"
        elif public_token and exp and exp.is_published:
            target_url = reverse('explorer:public_complex_building_view', args=[public_token, b.pk])

        hotspots.append({
            'id': hs.pk,
            'building_id': b.pk,
            'name': b.name,
            'block_number': b.block_number,
            'floor_count': b.floor_count,
            'polygon_points': hs.polygon_points or [],
            'label_x': hs.label_x,
            'label_y': hs.label_y,
            'stats': {'total': t_cnt, 'available': a_cnt, 'reserved': r_cnt, 'sold': s_cnt},
            'target_url': target_url,
            'is_ready': bool(exp and exp.hero_render),
        })

    return {
        'mode': 'complex',
        'is_crm': bool(include_crm_actions),
        'complex': {
            'id': complex_obj.pk,
            'name': complex_obj.name,
            'subtitle': complex_obj.subtitle,
            'description': complex_obj.description,
            'image_url': complex_obj.masterplan_image.url if complex_obj.masterplan_image else '',
            'image_width': complex_obj.image_width or 1600,
            'image_height': complex_obj.image_height or 1000,
            'summary': {
                'total': total_all,
                'available': avail_all,
                'reserved': res_all,
                'sold': sold_all,
            },
        },
        'hotspots': hotspots,
    }


@login_required
def explorer_index(request):
    """Hub listing all complexes & buildings with their Interactive Explorer setup status."""
    denied = _require_any_view_permission(request)
    if denied:
        return denied

    company = get_user_company(request.user)
    can_edit = has_permission(request.user, 'edit_buildings')

    complexes = list(
        ComplexExplorer.objects.filter(company=company).prefetch_related('building_hotspots')
    )
    buildings = list(Building.objects.filter(company=company).order_by('block_number', 'id'))
    explorers_by_b = {
        e.building_id: e
        for e in BuildingExplorer.objects.filter(building__company=company).prefetch_related('floors__hotspots')
    }

    building_cards = []
    for b in buildings:
        exp = explorers_by_b.get(b.pk)
        real_total = b.apartments.filter(is_real=True).count()
        avail_cnt = b.apartments.filter(is_real=True, status=Apartment.STATUS_AVAILABLE).count()
        mapped_cnt = 0
        floors_with_plans = 0
        if exp:
            for fe in exp.floors.all():
                if fe.plan_image:
                    floors_with_plans += 1
                mapped_cnt += sum(1 for h in fe.hotspots.all() if h.apartment_id)
        building_cards.append({
            'building': b,
            'explorer': exp,
            'real_total': real_total,
            'available_count': avail_cnt,
            'mapped_count': mapped_cnt,
            'floors_with_plans': floors_with_plans,
            'share_url': (
                request.build_absolute_uri(reverse('explorer:public_building_view', args=[exp.share_token]))
                if (exp and exp.is_published and exp.public_share_enabled)
                else ''
            ),
        })

    complex_cards = []
    for c in complexes:
        complex_cards.append({
            'complex': c,
            'hotspot_count': c.building_hotspots.count(),
            'share_url': (
                request.build_absolute_uri(reverse('explorer:public_complex_view', args=[c.share_token]))
                if (c.is_published and c.public_share_enabled)
                else ''
            ),
        })

    return render(request, 'explorer/index.html', {
        'complex_cards': complex_cards,
        'building_cards': building_cards,
        'can_edit': can_edit,
    })


@login_required
def explorer_building_view(request, building_pk):
    """Internal CRM interactive 3D render -> animated floor plan -> apartment contract handoff."""
    denied = _require_any_view_permission(request)
    if denied:
        return denied

    company = get_user_company(request.user)
    building = get_object_or_404(Building, pk=building_pk, company=company)
    explorer_obj = BuildingExplorer.objects.filter(building=building).first()

    can_edit = has_permission(request.user, 'edit_buildings')
    has_assets = bool(explorer_obj and (explorer_obj.hero_render or explorer_obj.floors.filter(plan_image__gt='').exists()))

    if not has_assets:
        if can_edit:
            messages.info(request, _("Upload a PDF album or exterior render + floor plan to configure the 3D Explorer."))
            return redirect('explorer:building_studio', building_pk=building.pk)
        return render(request, 'explorer/not_configured.html', {
            'building': building,
            'can_edit': can_edit,
        })

    fullscreen = request.GET.get('fullscreen') == '1'
    fs_suffix = '?fullscreen=1' if fullscreen else ''
    complex_back_url = ''
    complex_name = ''
    complex_q = request.GET.get('complex')
    if complex_q and complex_q.isdigit():
        c_obj = ComplexExplorer.objects.filter(pk=int(complex_q), company=company).first()
        if c_obj:
            complex_back_url = f"{reverse('explorer:complex_view', args=[c_obj.pk])}{fs_suffix}"
            complex_name = c_obj.name
    elif explorer_obj.complex_explorer and explorer_obj.complex_explorer.company_id == company.pk:
        complex_back_url = f"{reverse('explorer:complex_view', args=[explorer_obj.complex_explorer.pk])}{fs_suffix}"
        complex_name = explorer_obj.complex_explorer.name

    can_create_contracts = has_permission(request.user, 'create_contracts')
    payload = serialize_building_payload(
        explorer_obj,
        include_crm_actions=True,
        can_create_contracts=can_create_contracts,
        complex_back_url=complex_back_url,
        complex_name=complex_name,
    )

    return render(request, 'explorer/presentation.html', {
        'payload': payload,
        'explorer_obj': explorer_obj,
        'building': building,
        'can_edit': can_edit,
        'is_public': fullscreen,
        'is_fullscreen': fullscreen,
        'base_template': 'explorer/public_base.html' if fullscreen else 'base.html',
        'browser_title': f"{building.name}" + (f" — {_('Block')} {building.block_number}" if building.block_number else ''),
    })


@login_required
def explorer_complex_view(request, pk):
    """Internal CRM interactive complex masterplan overview."""
    denied = _require_any_view_permission(request)
    if denied:
        return denied

    company = get_user_company(request.user)
    complex_obj = get_object_or_404(ComplexExplorer, pk=pk, company=company)
    can_edit = has_permission(request.user, 'edit_buildings')

    if not complex_obj.masterplan_image and can_edit:
        messages.info(request, _("Upload or pick a complex overview image to place building blocks."))
        return redirect('explorer:complex_studio', pk=complex_obj.pk)

    fullscreen = request.GET.get('fullscreen') == '1'
    payload = serialize_complex_payload(complex_obj, include_crm_actions=True, fullscreen=fullscreen)
    return render(request, 'explorer/presentation.html', {
        'payload': payload,
        'complex_obj': complex_obj,
        'can_edit': can_edit,
        'is_public': fullscreen,
        'is_fullscreen': fullscreen,
        'base_template': 'explorer/public_base.html' if fullscreen else 'base.html',
        'browser_title': complex_obj.name,
    })


def public_building_view(request, token):
    """Public unauthenticated read-only presentation for stakeholders/clients (ZERO customer PII)."""
    explorer_obj = get_object_or_404(
        BuildingExplorer.objects.select_related('building'),
        share_token=token,
        is_published=True,
        public_share_enabled=True,
    )
    payload = serialize_building_payload(explorer_obj, include_crm_actions=False)
    return render(request, 'explorer/presentation.html', {
        'payload': payload,
        'explorer_obj': explorer_obj,
        'building': explorer_obj.building,
        'can_edit': False,
        'is_public': True,
        'is_fullscreen': True,
        'base_template': 'explorer/public_base.html',
        'page_title': f"{explorer_obj.building.name}",
    })


def public_complex_view(request, token):
    """Public unauthenticated read-only complex presentation."""
    complex_obj = get_object_or_404(
        ComplexExplorer,
        share_token=token,
        is_published=True,
        public_share_enabled=True,
    )
    payload = serialize_complex_payload(complex_obj, include_crm_actions=False, public_token=str(token))
    return render(request, 'explorer/presentation.html', {
        'payload': payload,
        'complex_obj': complex_obj,
        'can_edit': False,
        'is_public': True,
        'is_fullscreen': True,
        'base_template': 'explorer/public_base.html',
        'page_title': complex_obj.name,
    })


def public_complex_building_view(request, token, building_pk):
    """Navigate into a published block inside a published public complex link."""
    complex_obj = get_object_or_404(
        ComplexExplorer,
        share_token=token,
        is_published=True,
        public_share_enabled=True,
    )
    explorer_obj = get_object_or_404(
        BuildingExplorer.objects.select_related('building'),
        building_id=building_pk,
        building__company_id=complex_obj.company_id,
        is_published=True,
    )
    belongs = (
        explorer_obj.complex_explorer_id == complex_obj.pk
        or complex_obj.building_hotspots.filter(building_id=building_pk).exists()
    )
    if not belongs:
        raise Http404("Not found")

    back_url = reverse('explorer:public_complex_view', args=[token])
    payload = serialize_building_payload(
        explorer_obj,
        include_crm_actions=False,
        complex_back_url=back_url,
        complex_name=complex_obj.name,
    )
    return render(request, 'explorer/presentation.html', {
        'payload': payload,
        'explorer_obj': explorer_obj,
        'building': explorer_obj.building,
        'can_edit': False,
        'is_public': True,
        'is_fullscreen': True,
        'base_template': 'explorer/public_base.html',
        'page_title': f"{complex_obj.name} — {explorer_obj.building.name}",
    })


def _sync_floor_rows(explorer_obj: BuildingExplorer):
    existing = {fe.floor_number: fe for fe in explorer_obj.floors.all()}
    for fl in range(1, explorer_obj.building.floor_count + 1):
        if fl not in existing:
            FloorExplorer.objects.create(building_explorer=explorer_obj, floor_number=fl)


def _valid_polygon(pts) -> list[list[float]] | None:
    if not isinstance(pts, list) or len(pts) < 3:
        return None
    out = []
    for p in pts:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            return None
        try:
            x = round(max(0.0, min(100.0, float(p[0]))), 2)
            y = round(max(0.0, min(100.0, float(p[1]))), 2)
        except (TypeError, ValueError):
            return None
        out.append([x, y])
    return out


@login_required
@require_permission('edit_buildings')
def explorer_building_studio(request, building_pk):
    """Self-service Visual Setup Studio for one building (PDF auto-extract + facade slicer + polygon editor)."""
    _reject_pure_customer(request.user)
    company = get_user_company(request.user)
    building = get_object_or_404(Building, pk=building_pk, company=company)
    explorer_obj, _created = BuildingExplorer.objects.get_or_create(building=building)
    _sync_floor_rows(explorer_obj)

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        if action == 'upload_pdf':
            up = request.FILES.get('source_pdf')
            if not up or not up.name.lower().endswith('.pdf'):
                messages.error(request, _("Please upload a valid .pdf architectural album."))
                return redirect('explorer:building_studio', building_pk=building.pk)
            explorer_obj.source_pdf.save(f'b{building.pk}_album.pdf', up, save=True)
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as tmp:
                with explorer_obj.source_pdf.open('rb') as src:
                    for chunk in src.chunks():
                        tmp.write(chunk)
                tmp.flush()
                try:
                    summary = extract_building_from_pdf(explorer_obj, tmp.name)
                    messages.success(
                        request,
                        _("Extracted %(floors)s floors and matched %(matched)s/%(expected)s apartments!") % {
                            'floors': len(summary.get('floors_extracted', [])),
                            'matched': summary.get('matched_apartments', 0),
                            'expected': summary.get('expected_apartments', 0),
                        },
                    )
                except Exception as exc:
                    messages.error(request, _("PDF extraction failed: %(err)s") % {'err': exc})
            return redirect('explorer:building_studio', building_pk=building.pk)

        if action == 'upload_render':
            up = request.FILES.get('hero_render')
            if not up:
                messages.error(request, _("Select an image file for the exterior render."))
                return redirect('explorer:building_studio', building_pk=building.pk)
            try:
                img_bgr = decode_image_bytes(up.read())
                ok, buf = cv2.imencode('.png', img_bgr)
                if not ok:
                    raise ValueError("Image encoding failed")
                explorer_obj.hero_render.save(f'b{building.pk}_hero.png', ContentFile(buf.tobytes()), save=False)
                explorer_obj.hero_height, explorer_obj.hero_width = img_bgr.shape[:2]
                explorer_obj.extraction_status = BuildingExplorer.STATUS_READY
                explorer_obj.save()

                has_bands = explorer_obj.floors.exclude(facade_polygon=[]).exists()
                if not has_bands or request.POST.get('re_slice') == '1':
                    bands, faces = auto_detect_facade_bands_and_faces(img_bgr, building.floor_count)
                    explorer_obj.facade_faces = faces
                    for fe in explorer_obj.floors.all():
                        if fe.floor_number in bands:
                            fe.facade_polygon = bands[fe.floor_number]
                            fe.save(update_fields=['facade_polygon'])
                else:
                    bands = {
                        fe.floor_number: fe.facade_polygon
                        for fe in explorer_obj.floors.all()
                        if fe.facade_polygon
                    }
                wc = extract_facade_windows_and_canopy(img_bgr, bands, rel_prefix=f'b{building.pk}_hero')
                meta = dict(explorer_obj.ai_metadata or {})
                meta['windows_by_floor'] = wc['windows_by_floor']
                meta['canopy_path'] = wc['canopy_path']
                meta.pop('sunset_hero_path', None)
                meta.pop('night_hero_path', None)
                explorer_obj.ai_metadata = meta
                explorer_obj.save(update_fields=['facade_faces', 'ai_metadata', 'updated_at'])
                if explorer_obj.atmosphere_enabled and ai_vision.get_ai_provider_status().get('gemini_ready'):
                    try:
                        generate_building_atmosphere_renders(explorer_obj, save_model=True)
                    except Exception:
                        pass
                messages.success(request, _("Exterior render updated!"))
            except Exception as exc:
                messages.error(request, _("Invalid render image: %(err)s") % {'err': exc})
            return redirect('explorer:building_studio', building_pk=building.pk)

        if action == 'select_extra_render':
            rel_path = request.POST.get('render_path', '').strip()
            valid_paths = {er.get('path') for er in (explorer_obj.extra_renders or [])}
            if rel_path in valid_paths and default_storage.exists(rel_path):
                with default_storage.open(rel_path, 'rb') as fh:
                    img_bgr = decode_image_bytes(fh.read())
                ok, buf = cv2.imencode('.png', img_bgr)
                if ok:
                    explorer_obj.hero_render.save(f'b{building.pk}_hero.png', ContentFile(buf.tobytes()), save=False)
                    explorer_obj.hero_height, explorer_obj.hero_width = img_bgr.shape[:2]
                    explorer_obj.save()
                    if request.POST.get('re_slice') == '1':
                        bands, faces = auto_detect_facade_bands_and_faces(img_bgr, building.floor_count)
                        explorer_obj.facade_faces = faces
                        for fe in explorer_obj.floors.all():
                            if fe.floor_number in bands:
                                fe.facade_polygon = bands[fe.floor_number]
                                fe.save(update_fields=['facade_polygon'])
                    else:
                        bands = {
                            fe.floor_number: fe.facade_polygon
                            for fe in explorer_obj.floors.all()
                            if fe.facade_polygon
                        }
                    wc = extract_facade_windows_and_canopy(img_bgr, bands, rel_prefix=f'b{building.pk}_hero')
                    meta = dict(explorer_obj.ai_metadata or {})
                    meta['windows_by_floor'] = wc['windows_by_floor']
                    meta['canopy_path'] = wc['canopy_path']
                    meta.pop('sunset_hero_path', None)
                    meta.pop('night_hero_path', None)
                    explorer_obj.ai_metadata = meta
                    explorer_obj.save(update_fields=['facade_faces', 'ai_metadata', 'updated_at'])
                    if explorer_obj.atmosphere_enabled and ai_vision.get_ai_provider_status().get('gemini_ready'):
                        try:
                            generate_building_atmosphere_renders(explorer_obj, save_model=True)
                        except Exception:
                            pass
                    messages.success(request, _("Hero render switched cleanly."))
            return redirect('explorer:building_studio', building_pk=building.pk)

        if action == 'ai_analyze_facade':
            view_path = request.POST.get('view_path', '').strip()
            if view_path:
                res = analyze_view_overlay(explorer_obj, view_path)
                return JsonResponse(res, status=200 if res.get('ok') else 400)
            res = auto_analyze_building_facade(explorer_obj)
            if res.get('ok'):
                bands_out = {
                    str(fe.floor_number): fe.facade_polygon
                    for fe in explorer_obj.floors.order_by('floor_number')
                }
                res['floors'] = bands_out
                res['facade_faces'] = explorer_obj.facade_faces or []
                return JsonResponse(res)
            return JsonResponse(res, status=400)

        if action == 'generate_atmosphere':
            res = generate_building_atmosphere_renders(explorer_obj)
            return JsonResponse(res, status=200 if res.get('ok') else 400)

        if action == 'save_view_bands':
            view_path = request.POST.get('view_path', '').strip()
            valid_paths = {er.get('path') for er in (explorer_obj.extra_renders or []) if er.get('sky_score', 0) >= 0}
            if view_path not in valid_paths:
                return JsonResponse({'ok': False, 'error': 'Unknown view'}, status=400)
            try:
                floors_map = (json.loads(request.POST.get('facade_bands_json', '') or '{}') or {}).get('floors', {})
            except Exception:
                return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)
            clean = {}
            for fe in explorer_obj.floors.all():
                poly = _valid_polygon(floors_map.get(str(fe.floor_number)))
                if poly:
                    clean[str(fe.floor_number)] = poly
            overlays = dict(explorer_obj.view_overlays or {})
            if clean:
                overlays[view_path] = {'floors': clean, 'source': 'manual'}
            else:
                overlays.pop(view_path, None)
            explorer_obj.view_overlays = overlays
            explorer_obj.save(update_fields=['view_overlays', 'updated_at'])
            return JsonResponse({'ok': True, 'updated': len(clean)})

        if action == 'save_facade_bands':
            raw = request.POST.get('facade_bands_json', '')
            try:
                data = json.loads(raw) if raw else {}
                floors_map = data.get('floors', {})
            except Exception:
                return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

            updated = 0
            bands_for_wc = {}
            for fe in explorer_obj.floors.all():
                poly_raw = floors_map.get(str(fe.floor_number))
                if poly_raw is None:
                    continue
                if poly_raw == []:
                    fe.facade_polygon = []
                    fe.save(update_fields=['facade_polygon'])
                    updated += 1
                    continue
                poly = _valid_polygon(poly_raw)
                if poly:
                    fe.facade_polygon = poly
                    fe.save(update_fields=['facade_polygon'])
                    bands_for_wc[fe.floor_number] = poly
                    updated += 1

            # Refresh glass window lighting rectangles against newly saved bands
            if bands_for_wc and explorer_obj.hero_render and default_storage.exists(explorer_obj.hero_render.name):
                with explorer_obj.hero_render.open('rb') as fh:
                    img_bgr = decode_image_bytes(fh.read())
                wc = extract_facade_windows_and_canopy(img_bgr, bands_for_wc, rel_prefix=f'b{building.pk}_hero')
                meta = dict(explorer_obj.ai_metadata or {})
                meta['windows_by_floor'] = wc['windows_by_floor']
                meta['canopy_path'] = wc['canopy_path']
                explorer_obj.ai_metadata = meta
                explorer_obj.save(update_fields=['ai_metadata', 'updated_at'])

            return JsonResponse({'ok': True, 'updated': updated})

        if action == 'upload_floor_plan':
            up = request.FILES.get('plan_file')
            try:
                fl_num = int(request.POST.get('floor_number', '1'))
            except ValueError:
                fl_num = 1
            extra_raw = request.POST.get('apply_to_floors', '').strip()
            target_floors = [fl_num]
            for part in extra_raw.split(','):
                part = part.strip()
                if part.isdigit():
                    val = int(part)
                    if 1 <= val <= building.floor_count and val not in target_floors:
                        target_floors.append(val)

            if not up:
                messages.error(request, _("Select a floor plan image or PDF page."))
                return redirect('explorer:building_studio', building_pk=building.pk)

            try:
                if up.name.lower().endswith('.pdf'):
                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as tmp_pdf:
                        for chunk in up.chunks():
                            tmp_pdf.write(chunk)
                        tmp_pdf.flush()
                        with tempfile.TemporaryDirectory() as td:
                            out_p = os.path.join(td, 'single')
                            subprocess.check_call(
                                ['pdftoppm', '-r', '140', '-f', '1', '-l', '1', '-singlefile', '-png', tmp_pdf.name, out_p],
                                stderr=subprocess.DEVNULL,
                            )
                            plan_bgr = cv2.imread(f'{out_p}.png')
                            res = apply_floor_plan_extraction(
                                explorer_obj, target_floors, plan_bgr, pdf_path=tmp_pdf.name, page_num=1
                            )
                else:
                    plan_bgr = decode_image_bytes(up.read())
                    res = apply_floor_plan_extraction(explorer_obj, target_floors, plan_bgr)

                explorer_obj.extraction_status = BuildingExplorer.STATUS_READY
                explorer_obj.save(update_fields=['extraction_status', 'updated_at'])
                total_m = sum(v['matched'] for v in res.values())
                messages.success(request, _("Uploaded floor plan & matched %(cnt)s apartments.") % {'cnt': total_m})
            except Exception as exc:
                messages.error(request, _("Failed to process floor plan: %(err)s") % {'err': exc})
            return redirect(f"{reverse('explorer:building_studio', args=[building.pk])}?floor={fl_num}")

        if action == 'save_floor_hotspots':
            try:
                fl_num = int(request.POST.get('floor_number', '1'))
                payload = json.loads(request.POST.get('hotspots_json', '{}'))
                rows = payload.get('hotspots', [])
            except Exception:
                return JsonResponse({'ok': False, 'error': 'Invalid payload'}, status=400)

            floor_exp = get_object_or_404(FloorExplorer, building_explorer=explorer_obj, floor_number=fl_num)
            valid_apts = {
                a.pk: a
                for a in building.apartments.filter(is_real=True, floor_number=fl_num)
            }
            floor_all_apts = {
                a.pk: a
                for a in building.apartments.filter(is_real=True)
            }

            with transaction.atomic():
                floor_exp.hotspots.all().delete()
                new_items = []
                for item in rows:
                    poly = _valid_polygon(item.get('polygon_points'))
                    if not poly:
                        continue
                    apt_id = item.get('apartment_id')
                    apt_obj = None
                    if apt_id is not None and str(apt_id).isdigit():
                        aid = int(apt_id)
                        apt_obj = valid_apts.get(aid) or floor_all_apts.get(aid)
                    try:
                        lx = round(max(0.0, min(100.0, float(item.get('label_x', 50.0)))), 2)
                        ly = round(max(0.0, min(100.0, float(item.get('label_y', 50.0)))), 2)
                    except (TypeError, ValueError):
                        lx, ly = 50.0, 50.0
                    new_items.append(
                        ApartmentHotspot(
                            floor_explorer=floor_exp,
                            apartment=apt_obj,
                            polygon_points=poly,
                            label_x=lx,
                            label_y=ly,
                            detected_label=str(item.get('detected_label', ''))[:64],
                        )
                    )
                ApartmentHotspot.objects.bulk_create(new_items)
            return JsonResponse({'ok': True, 'saved': len(new_items)})

        if action == 'copy_floor_layout':
            try:
                src_num = int(request.POST.get('source_floor', '1'))
            except ValueError:
                src_num = 1
            src_floor = get_object_or_404(FloorExplorer, building_explorer=explorer_obj, floor_number=src_num)
            targets_raw = request.POST.getlist('target_floors')
            if not targets_raw and request.POST.get('target_floors_csv'):
                targets_raw = [p.strip() for p in request.POST.get('target_floors_csv', '').split(',') if p.strip()]
            target_nums = [int(t) for t in targets_raw if str(t).isdigit() and int(t) != src_num]
            target_objs = list(explorer_obj.floors.filter(floor_number__in=target_nums))
            cnt = copy_floor_layout_to_targets(src_floor, target_objs)
            messages.success(request, _("Copied floor %(src)s layout to %(cnt)s floors.") % {'src': src_num, 'cnt': cnt})
            return redirect(f"{reverse('explorer:building_studio', args=[building.pk])}?floor={src_num}")

        if action == 'update_settings':
            explorer_obj.is_published = request.POST.get('is_published') == 'on'
            explorer_obj.public_share_enabled = request.POST.get('public_share_enabled') == 'on'
            explorer_obj.atmosphere_enabled = request.POST.get('atmosphere_enabled') == 'on'
            try:
                compass_val = float(request.POST.get('compass_angle', explorer_obj.compass_angle or 0.0))
                explorer_obj.compass_angle = compass_val % 360.0
            except (TypeError, ValueError):
                pass
            c_id = request.POST.get('complex_explorer', '').strip()
            if c_id.isdigit():
                c_obj = ComplexExplorer.objects.filter(pk=int(c_id), company=company).first()
                explorer_obj.complex_explorer = c_obj
            else:
                explorer_obj.complex_explorer = None
            if request.POST.get('regenerate_token') == '1':
                explorer_obj.share_token = uuid.uuid4()
            explorer_obj.save()
            messages.success(request, _("Presentation settings updated."))
            return redirect('explorer:building_studio', building_pk=building.pk)

    try:
        active_floor = int(request.GET.get('floor', '1'))
    except ValueError:
        active_floor = 1
    if active_floor < 1 or active_floor > building.floor_count:
        active_floor = 1

    floors_list = list(explorer_obj.floors.prefetch_related('hotspots__apartment').order_by('floor_number'))
    all_real_apts = list(building.apartments.filter(is_real=True).order_by('floor_number', 'entrance_number', 'id'))

    studio_data = {
        'building_id': building.pk,
        'floor_count': building.floor_count,
        'active_floor': active_floor,
        'compass_angle': float(explorer_obj.compass_angle or 0.0),
        'hero_render_url': explorer_obj.hero_render.url if explorer_obj.hero_render else '',
        'hero_width': explorer_obj.hero_width or 1600,
        'hero_height': explorer_obj.hero_height or 1000,
        'facade_faces': explorer_obj.facade_faces or [],
        'floors': [
            {
                'floor_number': fe.floor_number,
                'facade_polygon': fe.facade_polygon or [],
                'plan_image_url': fe.plan_image.url if fe.plan_image else '',
                'plan_width': fe.plan_width or 1600,
                'plan_height': fe.plan_height or 1000,
                'hotspots': [
                    {
                        'id': hs.pk,
                        'apartment_id': hs.apartment_id,
                        'polygon_points': hs.polygon_points,
                        'label_x': hs.label_x,
                        'label_y': hs.label_y,
                        'detected_label': hs.detected_label,
                    }
                    for hs in fe.hotspots.all()
                ],
                'apartments': [
                    {
                        'id': a.pk,
                        'apartment_number': str(a.apartment_number),
                        'total_area': str(a.total_area),
                        'living_room_count': a.living_room_count,
                        'status': a.status,
                    }
                    for a in all_real_apts
                    if a.floor_number == fe.floor_number
                ],
            }
            for fe in floors_list
        ],
    }

    extra_renders = [
        {
            'path': er.get('path', ''),
            'url': _safe_storage_url(er.get('path', '')),
            'label': er.get('label', 'View'),
            'width': er.get('width', 1600),
            'height': er.get('height', 1000),
            'floors': ((explorer_obj.view_overlays or {}).get(er.get('path', '')) or {}).get('floors') or {},
        }
        for er in (explorer_obj.extra_renders or [])
        if er.get('path') and er.get('sky_score', 0) >= 0 and default_storage.exists(er.get('path'))
    ]
    studio_data['extra_renders'] = extra_renders

    public_url = (
        request.build_absolute_uri(reverse('explorer:public_building_view', args=[explorer_obj.share_token]))
        if (explorer_obj.is_published and explorer_obj.public_share_enabled)
        else ''
    )

    ai_meta = explorer_obj.ai_metadata or {}
    windows_total = sum(len(v) for v in (ai_meta.get('windows_by_floor') or {}).values())

    return render(request, 'explorer/studio.html', {
        'building': building,
        'explorer_obj': explorer_obj,
        'studio_data': studio_data,
        'floors_list': floors_list,
        'extra_renders': extra_renders,
        'company_complexes': ComplexExplorer.objects.filter(company=company),
        'public_url': public_url,
        'ai_status': ai_vision.get_ai_provider_status(),
        'windows_total': windows_total,
        'has_canopy': bool(ai_meta.get('canopy_path')),
    })


@login_required
@require_permission('edit_buildings')
def explorer_complex_create(request):
    """Create a multi-block ComplexExplorer overview."""
    _reject_pure_customer(request.user)
    company = get_user_company(request.user)
    render_library = _collect_company_render_library(company)

    if request.method == 'POST':
        form = ComplexExplorerForm(request.POST, request.FILES)
        if form.is_valid():
            c_obj = form.save(commit=False)
            c_obj.company = company
            picked_path = request.POST.get('library_render_path', '').strip()
            valid_paths = {item['path'] for item in render_library}

            if c_obj.masterplan_image:
                raw = c_obj.masterplan_image.read()
                img = decode_image_bytes(raw)
                c_obj.image_height, c_obj.image_width = img.shape[:2]
                c_obj.save()
            elif picked_path in valid_paths and default_storage.exists(picked_path):
                with default_storage.open(picked_path, 'rb') as fh:
                    raw = fh.read()
                img = decode_image_bytes(raw)
                c_obj.image_height, c_obj.image_width = img.shape[:2]
                c_obj.masterplan_image.save(f'complex_{uuid.uuid4().hex[:8]}.png', ContentFile(raw), save=False)
                c_obj.save()
            elif c_obj.masterplan_pdf:
                # Complex-first workflow: user uploaded only masterplan PDF first -> render page 1 preview
                c_obj.save()
                try:
                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as tmp:
                        with c_obj.masterplan_pdf.open('rb') as src:
                            for ch in src.chunks():
                                tmp.write(ch)
                        tmp.flush()
                        with tempfile.TemporaryDirectory() as td:
                            out_p = os.path.join(td, 'mp1')
                            subprocess.check_call(
                                ['pdftoppm', '-r', '130', '-f', '1', '-l', '1', '-singlefile', '-png', tmp.name, out_p],
                                stderr=subprocess.DEVNULL,
                            )
                            if os.path.exists(f'{out_p}.png'):
                                png_bytes = open(f'{out_p}.png', 'rb').read()
                                img = decode_image_bytes(png_bytes)
                                c_obj.image_height, c_obj.image_width = img.shape[:2]
                                c_obj.masterplan_image.save(f'complex_{c_obj.pk}.png', ContentFile(png_bytes), save=False)
                                c_obj.save()
                except Exception:
                    pass
            else:
                c_obj.save()

            messages.success(request, _("Complex Overview created! Draw or AI-match clickable block regions."))
            return redirect('explorer:complex_studio', pk=c_obj.pk)
    else:
        form = ComplexExplorerForm()

    return render(request, 'explorer/complex_create.html', {
        'form': form,
        'render_library': render_library,
    })


@login_required
@require_permission('edit_buildings')
def explorer_complex_studio(request, pk):
    """Visual Setup Studio for ComplexExplorer (masterplan image + building polygons + AI matcher + share toggle)."""
    _reject_pure_customer(request.user)
    company = get_user_company(request.user)
    complex_obj = get_object_or_404(ComplexExplorer, pk=pk, company=company)
    render_library = _collect_company_render_library(company)

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        if action == 'update_masterplan':
            up = request.FILES.get('masterplan_image')
            up_pdf = request.FILES.get('masterplan_pdf')
            picked_path = request.POST.get('library_render_path', '').strip()
            valid_paths = {item['path'] for item in render_library}

            complex_obj.name = request.POST.get('name', complex_obj.name).strip() or complex_obj.name
            complex_obj.subtitle = request.POST.get('subtitle', '').strip()
            complex_obj.description = request.POST.get('description', '').strip()

            if up:
                img = decode_image_bytes(up.read())
                ok, buf = cv2.imencode('.png', img)
                if ok:
                    complex_obj.masterplan_image.save(f'complex_{complex_obj.pk}.png', ContentFile(buf.tobytes()), save=False)
                    complex_obj.image_height, complex_obj.image_width = img.shape[:2]
            elif picked_path in valid_paths and default_storage.exists(picked_path):
                with default_storage.open(picked_path, 'rb') as fh:
                    raw = fh.read()
                img = decode_image_bytes(raw)
                complex_obj.masterplan_image.save(f'complex_{complex_obj.pk}.png', ContentFile(raw), save=False)
                complex_obj.image_height, complex_obj.image_width = img.shape[:2]

            if up_pdf and up_pdf.name.lower().endswith('.pdf'):
                complex_obj.masterplan_pdf.save(f'complex_{complex_obj.pk}_mp.pdf', up_pdf, save=False)

            complex_obj.save()
            messages.success(request, _("Complex details updated."))
            return redirect('explorer:complex_studio', pk=complex_obj.pk)

        if action == 'ai_detect_blocks':
            res = auto_detect_complex_blocks(complex_obj)
            status_code = 200 if res.get('ok') else (400 if not res.get('needs_key') else 422)
            return JsonResponse(res, status=status_code)

        if action == 'save_building_hotspots':
            try:
                data = json.loads(request.POST.get('hotspots_json', '{}'))
                rows = data.get('hotspots', [])
            except Exception:
                return JsonResponse({'ok': False, 'error': 'Invalid payload'}, status=400)

            valid_buildings = {b.pk: b for b in Building.objects.filter(company=company)}
            with transaction.atomic():
                complex_obj.building_hotspots.all().delete()
                seen_buildings = set()
                created_items = []
                for item in rows:
                    bid = item.get('building_id')
                    if not bid or not str(bid).isdigit():
                        continue
                    b_obj = valid_buildings.get(int(bid))
                    if not b_obj or b_obj.pk in seen_buildings:
                        continue
                    poly = _valid_polygon(item.get('polygon_points'))
                    if not poly:
                        continue
                    seen_buildings.add(b_obj.pk)
                    lx = round(max(0.0, min(100.0, float(item.get('label_x', 50.0)))), 2)
                    ly = round(max(0.0, min(100.0, float(item.get('label_y', 50.0)))), 2)
                    conf_val = item.get('ai_confidence')
                    try:
                        conf_val = float(conf_val) if conf_val is not None else None
                    except (TypeError, ValueError):
                        conf_val = None
                    created_items.append(
                        ComplexBuildingHotspot(
                            complex_explorer=complex_obj,
                            building=b_obj,
                            polygon_points=poly,
                            label_x=lx,
                            label_y=ly,
                            ai_confidence=conf_val,
                            ai_notes=str(item.get('ai_notes', ''))[:255],
                        )
                    )
                    # Link BuildingExplorer back to this ComplexExplorer
                    BuildingExplorer.objects.filter(building=b_obj).update(complex_explorer=complex_obj)
                ComplexBuildingHotspot.objects.bulk_create(created_items)
            return JsonResponse({'ok': True, 'saved': len(created_items)})

        if action == 'update_settings':
            complex_obj.is_published = request.POST.get('is_published') == 'on'
            complex_obj.public_share_enabled = request.POST.get('public_share_enabled') == 'on'
            if request.POST.get('regenerate_token') == '1':
                complex_obj.share_token = uuid.uuid4()
            complex_obj.save()
            messages.success(request, _("Complex share settings saved."))
            return redirect('explorer:complex_studio', pk=complex_obj.pk)

    company_buildings = list(Building.objects.filter(company=company).order_by('block_number', 'id'))
    explorers_map = {
        e.building_id: e
        for e in BuildingExplorer.objects.filter(building__in=company_buildings)
    }
    studio_data = {
        'complex_id': complex_obj.pk,
        'image_url': complex_obj.masterplan_image.url if complex_obj.masterplan_image else '',
        'image_width': complex_obj.image_width or 1600,
        'image_height': complex_obj.image_height or 1000,
        'compass_angle': float(complex_obj.compass_angle or 0.0),
        'buildings': [
            {
                'id': b.pk,
                'name': b.name,
                'block_number': b.block_number,
                'floor_count': b.floor_count,
                'has_keymap': bool(
                    explorers_map.get(b.pk)
                    and (explorers_map[b.pk].ai_metadata or {}).get('keymap_path')
                ),
            }
            for b in company_buildings
        ],
        'hotspots': [
            {
                'building_id': hs.building_id,
                'polygon_points': hs.polygon_points,
                'label_x': hs.label_x,
                'label_y': hs.label_y,
                'ai_confidence': hs.ai_confidence,
                'ai_notes': hs.ai_notes,
            }
            for hs in complex_obj.building_hotspots.all()
        ],
    }

    public_url = (
        request.build_absolute_uri(reverse('explorer:public_complex_view', args=[complex_obj.share_token]))
        if (complex_obj.is_published and complex_obj.public_share_enabled)
        else ''
    )

    return render(request, 'explorer/complex_studio.html', {
        'complex_obj': complex_obj,
        'render_library': render_library,
        'studio_data': studio_data,
        'public_url': public_url,
        'ai_status': ai_vision.get_ai_provider_status(),
    })

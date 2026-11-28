import datetime
import io
import json
import tempfile
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from building.models import Apartment, Building
from contract.models import Contract
from explorer.models import (
    ApartmentHotspot,
    BuildingExplorer,
    ComplexBuildingHotspot,
    ComplexExplorer,
    FloorExplorer,
)
from explorer.services import ai_vision
from explorer.services.extraction import (
    linear_sum_assignment_numpy,
    match_regions_to_apartments,
    segment_floor_plan,
    slice_facade_into_floors,
)
from explorer.services.spatial_matcher import (
    extract_facade_windows_and_canopy,
    extract_red_keymap_crop,
    slice_multiface_facade,
)
from users.models import CompanyProfile, CustomUser, Role, StaffProfile


def _make_png_bytes(width=900, height=600, color=(200, 180, 150)) -> bytes:
    img = np.full((height, width, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode('.png', img)
    assert ok
    return buf.tobytes()


def _make_synthetic_floor_plan(width=1200, height=850) -> np.ndarray:
    """Create a synthetic white architectural sheet with 3 distinct pastel colored apartments."""
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    # Three distinct colored apartment blocks (HSV S > 22, V > 140)
    cv2.rectangle(img, (120, 140), (390, 640), (207, 183, 171), -1)   # Unit A (largest)
    cv2.rectangle(img, (440, 140), (740, 520), (195, 231, 201), -1)   # Unit B (medium)
    cv2.rectangle(img, (790, 140), (1050, 440), (177, 171, 249), -1)  # Unit C (smallest)
    # Draw thin dark interior partition lines inside Unit A to verify gap-bridging
    cv2.line(img, (250, 140), (250, 460), (40, 40, 40), 3)
    return img


class ExplorerTests(TestCase):
    def setUp(self):
        self.tmp_media = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_media.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.tmp_media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.client = Client(SERVER_NAME='localhost')
        self.company_a = CustomUser.objects.create_user(
            phone_number='+998906000001', password='password123', full_name='Alpha Dev', is_company=True
        )
        CompanyProfile.objects.create(user=self.company_a, company_name='Alpha Dev LLC')

        self.company_b = CustomUser.objects.create_user(
            phone_number='+998906000002', password='password123', full_name='Beta Dev', is_company=True
        )
        CompanyProfile.objects.create(user=self.company_b, company_name='Beta Dev LLC')

        self.customer = CustomUser.objects.create_user(
            phone_number='+998906000003',
            password='password123',
            full_name='Secret Buyer Name',
            passport_series='AD9988776',
            is_customer=True,
        )

        # Read-only sales manager: can view contracts & create contracts, CANNOT edit buildings/studio
        sales_role = Role.objects.create(
            company=self.company_a,
            name='Sales Presenter',
            permissions=['view_contracts', 'create_contracts'],
        )
        self.sales_staff = CustomUser.objects.create_user(
            phone_number='+998906000004', password='password123', full_name='Sales Staff', is_staff_member=True
        )
        StaffProfile.objects.create(user=self.sales_staff, company=self.company_a, role=sales_role)

        self.building = Building.objects.create(
            company=self.company_a,
            name='Nur Tower',
            block_number='1',
            address='Samarkand',
            floor_count=3,
            entrance_count=1,
            apartments_per_floor=3,
        )
        self.apts = []
        apt_num = 1
        specs = [(Decimal('75.00'), 2), (Decimal('55.00'), 2), (Decimal('36.00'), 1)]
        for fl in range(1, 4):
            for area, rooms in specs:
                self.apts.append(
                    Apartment.objects.create(
                        building=self.building,
                        apartment_number=str(apt_num),
                        floor_number=fl,
                        entrance_number=1,
                        living_room_count=rooms,
                        total_area=area,
                        living_area=area - Decimal('8.00'),
                        status=Apartment.STATUS_AVAILABLE,
                    )
                )
                apt_num += 1

        # Sell Apartment #1 on Floor 1 to create confidential Contract data
        self.sold_apt = self.apts[0]
        self.sold_apt.status = Apartment.STATUS_SOLD
        self.sold_apt.save(update_fields=['status'])
        Contract.objects.create(
            apartment=self.sold_apt,
            customer=self.customer,
            company=self.company_a,
            contract_id=901,
            contract_date=datetime.date(2026, 11, 1),
            price_per_square=Decimal('10000000.00'),
            total_amount=Decimal('500000000.00'),
            payment_months=12,
        )

    def test_hungarian_assignment_rectangular_and_square(self):
        cost_wide = np.array([
            [10.0, 2.0, 9.0, 4.0],
            [3.0, 8.0, 7.0, 1.0],
        ])
        rows, cols = linear_sum_assignment_numpy(cost_wide)
        self.assertEqual((rows, cols), ([0, 1], [1, 3]))

        cost_tall = np.array([
            [9.0, 1.0],
            [2.0, 8.0],
            [7.0, 6.0],
        ])
        rows2, cols2 = linear_sum_assignment_numpy(cost_tall)
        self.assertEqual((rows2, cols2), ([0, 1], [1, 0]))

    def test_color_segmentation_and_rotated_pdf_matching(self):
        plan_img = _make_synthetic_floor_plan()
        seg = segment_floor_plan(plan_img)
        self.assertEqual(len(seg['regions']), 3)
        self.assertLess(seg['crop_width'], plan_img.shape[1])

        # Simulated rotated PDF words: unrotated page size is portrait 842x1191 while image is landscape 1200x850
        # Place '1' next to 'комн.' inside Unit C to prove room-label disambiguation!
        fake_xml = (
            '<page width="842.0" height="1191.0">'
            '<word xMin="240.0" yMin="300.0" xMax="260.0" yMax="320.0">1</word>'
            '<word xMin="240.0" yMin="340.0" xMax="280.0" yMax="355.0">75.00</word>'
            '<word xMin="570.0" yMin="300.0" xMax="590.0" yMax="320.0">2</word>'
            '<word xMin="570.0" yMin="340.0" xMax="610.0" yMax="355.0">55.00</word>'
            '<word xMin="890.0" yMin="260.0" xMax="900.0" yMax="272.0">1</word>'
            '<word xMin="906.0" yMin="260.0" xMax="945.0" yMax="272.0">комн.</word>'
            '<word xMin="910.0" yMin="300.0" xMax="930.0" yMax="320.0">3</word>'
            '<word xMin="905.0" yMin="340.0" xMax="945.0" yMax="355.0">36.00</word>'
            '</page>'
        )
        fl1_apts = [a for a in self.apts if a.floor_number == 1]
        with patch('explorer.services.extraction.subprocess.check_output', return_value=fake_xml):
            matched = match_regions_to_apartments(seg, fl1_apts, pdf_path='/tmp/fake.pdf', page_num=3)

        self.assertEqual(len(matched), 3)
        matched_nums = sorted(v[0].apartment_number for v in matched.values())
        self.assertEqual(matched_nums, ['1', '2', '3'])

    @override_settings(AI_ENABLED=False, AI_API_KEY='', GEMINI_API_KEY='')
    def test_deepseek_ai_vision_fallback_mocked_and_disabled_graceful(self):
        png = _make_png_bytes(300, 200)
        # Disabled -> cleanly returns None
        self.assertIsNone(ai_vision.match_regions_with_ai(png, [{'apartment_number': '1', 'total_area': '75', 'rooms': 2}]))
        self.assertIsNone(ai_vision.estimate_facade_bounds_with_ai(png, 5))

        # Mock enabled DeepSeek/OpenAI client returning valid JSON
        fake_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='```json\n{"matches": {"1": "1", "2": "2"}}\n```'))]
        )
        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: fake_resp)))
        with override_settings(AI_ENABLED=True, AI_API_KEY='test-key', AI_BASE_URL='https://api.deepseek.com', GEMINI_API_KEY=''):
            with patch('openai.OpenAI', return_value=fake_client):
                res = ai_vision.match_regions_with_ai(
                    png,
                    [
                        {'apartment_number': '1', 'total_area': '75.00', 'rooms': 2},
                        {'apartment_number': '2', 'total_area': '55.00', 'rooms': 2},
                    ],
                )
        self.assertEqual(res, {1: '1', 2: '2'})

    def test_studio_permissions_and_multi_tenant_isolation(self):
        # Cross-tenant Company B gets 404 on Company A's studio and building view
        self.client.force_login(self.company_b)
        self.assertEqual(self.client.get(reverse('explorer:building_studio', args=[self.building.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('explorer:building_view', args=[self.building.pk])).status_code, 404)

        # Customer gets 404 on internal CRM routes
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse('explorer:index')).status_code, 404)
        self.assertEqual(self.client.get(reverse('explorer:building_view', args=[self.building.pk])).status_code, 404)

        # Sales staff (view_contracts + create_contracts, NO edit_buildings) is blocked from Studio
        self.client.force_login(self.sales_staff)
        studio_resp = self.client.get(reverse('explorer:building_studio', args=[self.building.pk]))
        self.assertNotEqual(studio_resp.status_code, 200)

        # Configure BuildingExplorer for Company A so sales_staff can view presentation & see Create Contract link
        exp = BuildingExplorer.objects.create(building=self.building, is_published=True)
        exp.hero_render.save('hero.png', SimpleUploadedFile('hero.png', _make_png_bytes(), content_type='image/png'))
        fe1 = FloorExplorer.objects.create(
            building_explorer=exp,
            floor_number=1,
            facade_polygon=[[10, 50], [90, 50], [90, 75], [10, 75]],
        )
        ApartmentHotspot.objects.create(
            floor_explorer=fe1,
            apartment=self.apts[1],  # Available Apt #2
            polygon_points=[[20, 20], [40, 20], [40, 40], [20, 40]],
            label_x=30.0,
            label_y=30.0,
        )
        view_resp = self.client.get(reverse('explorer:building_view', args=[self.building.pk]))
        self.assertEqual(view_resp.status_code, 200)
        self.assertContains(view_resp, reverse('contract:create') + f'?apartment={self.apts[1].pk}')

    def test_facade_slicer_floor_hotspot_save_and_copy_layout(self):
        self.client.force_login(self.company_a)
        studio_url = reverse('explorer:building_studio', args=[self.building.pk])

        # Open Studio (auto-creates BuildingExplorer + FloorExplorers 1..3)
        self.assertEqual(self.client.get(studio_url).status_code, 200)
        exp = BuildingExplorer.objects.get(building=self.building)
        self.assertEqual(exp.floors.count(), 3)

        # Save sliced facade bands
        bands = slice_facade_into_floors((10, 20), (90, 20), (90, 80), (10, 80), 3)
        band_resp = self.client.post(studio_url, {
            'action': 'save_facade_bands',
            'facade_bands_json': json.dumps({'floors': {str(k): v for k, v in bands.items()}}),
        })
        self.assertEqual(band_resp.status_code, 200)
        self.assertTrue(band_resp.json()['ok'])
        self.assertEqual(FloorExplorer.objects.get(building_explorer=exp, floor_number=2).facade_polygon, bands[2])

        # Upload synthetic floor plan on Floor 1
        plan_png = cv2.imencode('.png', _make_synthetic_floor_plan())[1].tobytes()
        up_resp = self.client.post(studio_url, {
            'action': 'upload_floor_plan',
            'floor_number': '1',
            'plan_file': SimpleUploadedFile('floor1.png', plan_png, content_type='image/png'),
        })
        self.assertEqual(up_resp.status_code, 302)
        f1 = FloorExplorer.objects.get(building_explorer=exp, floor_number=1)
        self.assertTrue(bool(f1.plan_image))
        self.assertEqual(f1.hotspots.count(), 3)

        # Save explicit apartment mappings for Floor 1 hotspots, then copy to Floors 2 & 3
        fl1_apts = list(self.building.apartments.filter(floor_number=1).order_by('id'))
        hs_payload = [
            {
                'apartment_id': fl1_apts[idx].pk,
                'polygon_points': [[10 + idx * 20, 10], [25 + idx * 20, 10], [25 + idx * 20, 40], [10 + idx * 20, 40]],
                'label_x': 15 + idx * 20,
                'label_y': 25,
                'detected_label': f'Unit {idx + 1}',
            }
            for idx in range(3)
        ]
        save_hs = self.client.post(studio_url, {
            'action': 'save_floor_hotspots',
            'floor_number': '1',
            'hotspots_json': json.dumps({'hotspots': hs_payload}),
        })
        self.assertEqual(save_hs.status_code, 200)
        self.assertEqual(save_hs.json()['saved'], 3)

        copy_resp = self.client.post(studio_url, {
            'action': 'copy_floor_layout',
            'source_floor': '1',
            'target_floors': ['2', '3'],
        })
        self.assertEqual(copy_resp.status_code, 302)
        f2 = FloorExplorer.objects.get(building_explorer=exp, floor_number=2)
        f3 = FloorExplorer.objects.get(building_explorer=exp, floor_number=3)
        self.assertEqual(f2.hotspots.filter(apartment__floor_number=2).count(), 3)
        self.assertEqual(f3.hotspots.filter(apartment__floor_number=3).count(), 3)

    def test_public_share_security_and_zero_pii_leak(self):
        exp = BuildingExplorer.objects.create(building=self.building, is_published=False, public_share_enabled=False)
        exp.hero_render.save('hero.png', SimpleUploadedFile('hero.png', _make_png_bytes(), content_type='image/png'))
        fe1 = FloorExplorer.objects.create(building_explorer=exp, floor_number=1, facade_polygon=[[10, 60], [90, 60], [90, 80], [10, 80]])
        ApartmentHotspot.objects.create(floor_explorer=fe1, apartment=self.sold_apt, polygon_points=[[10, 10], [30, 10], [30, 30], [10, 30]])

        pub_url = reverse('explorer:public_building_view', args=[exp.share_token])
        # Disabled -> 404
        self.assertEqual(self.client.get(pub_url).status_code, 404)

        # Published without public_share_enabled -> 404
        exp.is_published = True
        exp.save()
        self.assertEqual(self.client.get(pub_url).status_code, 404)

        # Both enabled -> 200: displays buyer_name on SOLD units while strictly hiding phone, passport, prices, or CRM contract creation links
        exp.public_share_enabled = True
        exp.save()
        resp = self.client.get(pub_url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('SOLD', body)
        self.assertIn('Secret Buyer Name', body)
        self.assertNotIn('+998906000003', body)
        self.assertNotIn('AD9988776', body)
        self.assertNotIn('500000000', body)
        self.assertNotIn(reverse('contract:create'), body)

    def test_complex_overview_create_studio_and_public_share(self):
        exp = BuildingExplorer.objects.create(building=self.building, is_published=True, public_share_enabled=False)
        exp.hero_render.save('hero.png', SimpleUploadedFile('hero.png', _make_png_bytes(), content_type='image/png'))

        self.client.force_login(self.company_a)
        create_resp = self.client.post(reverse('explorer:complex_create'), {
            'name': 'Nur Complex',
            'subtitle': '5 Floors',
            'masterplan_image': SimpleUploadedFile('mp.png', _make_png_bytes(), content_type='image/png'),
        })
        self.assertEqual(create_resp.status_code, 302)
        cx = ComplexExplorer.objects.get(name='Nur Complex', company=self.company_a)

        # Save building hotspot
        save_resp = self.client.post(reverse('explorer:complex_studio', args=[cx.pk]), {
            'action': 'save_building_hotspots',
            'hotspots_json': json.dumps({
                'hotspots': [{'building_id': self.building.pk, 'polygon_points': [[15, 20], [50, 20], [50, 60], [15, 60]], 'label_x': 32, 'label_y': 40}]
            }),
        })
        self.assertEqual(save_resp.status_code, 200)
        self.assertEqual(ComplexBuildingHotspot.objects.filter(complex_explorer=cx, building=self.building).count(), 1)

        # Publish & share complex
        self.client.post(reverse('explorer:complex_studio', args=[cx.pk]), {
            'action': 'update_settings',
            'is_published': 'on',
            'public_share_enabled': 'on',
        })
        # Verify CRM fullscreen mode (?fullscreen=1) on both complex and building views
        fs_cx = self.client.get(reverse('explorer:complex_view', args=[cx.pk]) + '?fullscreen=1')
        self.assertEqual(fs_cx.status_code, 200)
        self.assertIn('fullscreen=1', fs_cx.content.decode('utf-8'))
        fs_bld = self.client.get(reverse('explorer:building_view', args=[self.building.pk]) + f'?complex={cx.pk}&fullscreen=1')
        self.assertEqual(fs_bld.status_code, 200)
        self.assertIn('paid_percentage', fs_bld.content.decode('utf-8'))
        self.client.logout()

        pub_cx = self.client.get(reverse('explorer:public_complex_view', args=[cx.share_token]))
        self.assertEqual(pub_cx.status_code, 200)
        pub_cx_bld = self.client.get(reverse('explorer:public_complex_building_view', args=[cx.share_token, self.building.pk]))
        self.assertEqual(pub_cx_bld.status_code, 200)
        self.assertNotIn('+998906000003', pub_cx_bld.content.decode('utf-8'))

    def test_v2_studio_floor_upload_and_no_3d_dollhouse_peel_ui(self):
        img = _make_synthetic_floor_plan(1200, 800)
        self.client.force_login(self.company_a)
        studio_url = reverse('explorer:building_studio', args=[self.building.pk])
        plan_png = cv2.imencode('.png', img)[1].tobytes()
        resp = self.client.post(studio_url, {
            'action': 'upload_floor_plan',
            'floor_number': '1',
            'plan_file': SimpleUploadedFile('cad_f1.png', plan_png, content_type='image/png'),
        })
        self.assertEqual(resp.status_code, 302)
        exp = BuildingExplorer.objects.get(building=self.building)
        f1 = FloorExplorer.objects.get(building_explorer=exp, floor_number=1)
        self.assertTrue(bool(f1.plan_image))
        self.assertGreaterEqual(f1.hotspots.count(), 3)

        # Save settings (compass_angle) cleanly and ensure Studio omits 3D rebuild UI
        set_resp = self.client.post(studio_url, {
            'action': 'update_settings',
            'is_published': 'on',
            'public_share_enabled': 'on',
            'atmosphere_enabled': 'on',
            'compass_angle': '90',
        })
        self.assertEqual(set_resp.status_code, 302)
        exp.refresh_from_db()
        self.assertEqual(exp.compass_angle, 90.0)

        studio_html = self.client.get(studio_url).content.decode('utf-8')
        self.assertNotIn('Rebuild 3D Models', studio_html)

        pres_html = self.client.get(reverse('explorer:building_view', args=[self.building.pk])).content.decode('utf-8')
        self.assertNotIn('3D Building Peel', pres_html)
        self.assertNotIn('3D Dollhouse', pres_html)
        self.assertNotIn('Inside Eye-Level', pres_html)
        self.assertNotIn('viewer3d.js', pres_html)

    def test_v2_keymap_guided_hero_picker_and_pro_facade_routing(self):
        fake_pick_resp = SimpleNamespace(
            status_code=200,
            text='ok',
            json=lambda: {
                'candidates': [{
                    'content': {
                        'parts': [{
                            'text': json.dumps({
                                'best_index': 1,
                                'camera_view': 'courtyard_north_to_south',
                                'reason': 'Block 1.1 right courtyard wing clearly framed',
                            })
                        }]
                    }
                }]
            },
        )
        fake_facade_resp = SimpleNamespace(
            status_code=200,
            text='ok',
            json=lambda: {
                'candidates': [{
                    'content': {
                        'parts': [{
                            'text': json.dumps({
                                'camera_view': 'courtyard_north_to_south',
                                'target_location_notes': 'Right wing matched to red keymap',
                                'faces': [
                                    {'tl': [710, 175], 'tr': [795, 178], 'br': [795, 310], 'bl': [710, 306]},
                                    {'tl': [798, 178], 'tr': [925, 275], 'br': [925, 405], 'bl': [798, 312]},
                                ],
                                'is_closeup': False,
                            })
                        }]
                    }
                }]
            },
        )
        with override_settings(GEMINI_API_KEY='fake-gemini-key', GEMINI_PRO_MODEL='gemini-4-carbon'):
            with patch('explorer.services.ai_vision.httpx.post', side_effect=[fake_pick_resp, fake_facade_resp]) as m_post:
                pick = ai_vision.select_best_hero_render_with_ai(
                    [(0, _make_png_bytes(400, 300)), (1, _make_png_bytes(400, 300))],
                    block_label='NUR AVENUE 2 (Block 1.1)',
                    keymap_bytes=_make_png_bytes(200, 200),
                    genplan_bytes=_make_png_bytes(400, 300),
                )
                self.assertIsNotNone(pick)
                self.assertEqual(pick['best_index'], 1)
                self.assertIn('gemini-4-carbon', m_post.call_args_list[0].args[0])

                fac = ai_vision.detect_facade_and_faces_with_ai(
                    _make_png_bytes(800, 500),
                    5,
                    building_label='NUR AVENUE 2 (Block 1.1)',
                    keymap_bytes=_make_png_bytes(200, 200),
                    genplan_bytes=_make_png_bytes(400, 300),
                    complex_buildings=[{'id': 1, 'block_number': '1'}, {'id': 2, 'block_number': '1.1'}],
                )
                self.assertIsNotNone(fac)
                self.assertEqual(len(fac['faces']), 2)
                # Seam continuity snap between face[0].tr/br and face[1].tl/bl
                self.assertEqual(fac['faces'][0]['tr'], fac['faces'][1]['tl'])
                self.assertEqual(fac['faces'][0]['br'], fac['faces'][1]['bl'])
                self.assertIn('gemini-4-carbon', m_post.call_args_list[1].args[0])

        # Also verify 3-face / 2-bend vertical_edges chain (L-shaped wing with inner concave + outer convex bend)
        faces_3 = ai_vision._parse_faces_from_ai_payload({
            'vertical_edges': [
                {'role': 'left_seam', 'top': [722, 175], 'bottom': [710, 308]},
                {'role': 'inner_concave_corner', 'top': [796, 177], 'bottom': [776, 311]},
                {'role': 'outer_convex_corner', 'top': [820, 290], 'bottom': [794, 414]},
                {'role': 'right_outer_edge', 'top': [923, 295], 'bottom': [889, 418]},
            ]
        })
        self.assertEqual(len(faces_3), 3)
        self.assertEqual(faces_3[0]['tr'], faces_3[1]['tl'])
        self.assertEqual(faces_3[1]['tr'], faces_3[2]['tl'])
        bands_3 = slice_multiface_facade(faces_3, floor_count=5)
        self.assertEqual(len(bands_3), 5)
        self.assertEqual(len(bands_3[3]), 8)  # 4 top vertices + 4 bottom vertices = 2 corner bends

    def test_v2_phase2_gemini_hybrid_keymap_windows_canopy_and_multiface(self):
        # 1. Verify multi-face corner slicing wraps continuously (6 vertices for 2 angled wings)
        faces = [
            {'tl': [10.0, 25.0], 'tr': [50.0, 20.0], 'br': [50.0, 75.0], 'bl': [10.0, 72.0]},
            {'tl': [50.0, 20.0], 'tr': [90.0, 28.0], 'br': [90.0, 72.0], 'bl': [50.0, 75.0]},
        ]
        bands = slice_multiface_facade(faces, floor_count=4)
        self.assertEqual(len(bands), 4)
        self.assertEqual(len(bands[1]), 6)

        # 2. Verify red corner key-map detection + cropping
        sheet = np.full((800, 1100, 3), 255, dtype=np.uint8)
        cv2.rectangle(sheet, (820, 560), (1040, 740), (30, 30, 30), 2)
        cv2.rectangle(sheet, (920, 620), (985, 690), (20, 20, 235), -1)  # Bright red block (BGR)
        km_bytes = extract_red_keymap_crop(sheet)
        self.assertIsNotNone(km_bytes)
        km_img = cv2.imdecode(np.frombuffer(km_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(km_img)
        self.assertGreater(km_img.shape[0], 40)

        # 3. Verify dark window detection + foreground green foliage canopy mask separation
        facade_img = np.full((600, 1000, 3), 220, dtype=np.uint8)  # Light stone wall
        # Draw dark glass windows inside Floor 2 (top) and Floor 1 (bottom)
        cv2.rectangle(facade_img, (180, 220), (235, 290), (40, 42, 46), -1)
        cv2.rectangle(facade_img, (320, 220), (375, 290), (40, 42, 46), -1)
        cv2.rectangle(facade_img, (180, 360), (235, 430), (40, 42, 46), -1)
        # Draw bright green street tree foliage overlapping Floor 1 right window area
        cv2.circle(facade_img, (550, 400), 65, (45, 165, 50), -1)
        f_bands = slice_facade_into_floors((10.0, 30.0), (90.0, 30.0), (90.0, 78.0), (10.0, 78.0), 2)
        wc = extract_facade_windows_and_canopy(facade_img, f_bands, rel_prefix='test_wc')
        self.assertTrue(len(wc['windows_by_floor']) >= 1)
        self.assertTrue(bool(wc['canopy_path']))

        # 4. Verify Gemini Spatial JSON client + Complex Studio ai_detect_blocks (mocked httpx)
        cx = ComplexExplorer.objects.create(company=self.company_a, name='Gemini Complex')
        cx.masterplan_image.save('cx.png', SimpleUploadedFile('cx.png', _make_png_bytes(1000, 600), content_type='image/png'))

        # Mock Gemini responses cleanly: block matcher JSON then compass JSON
        fake_match_resp = SimpleNamespace(
            status_code=200,
            text='ok',
            json=lambda: {
                'candidates': [{
                    'content': {
                        'parts': [{
                            'text': json.dumps({
                                'blocks': [{
                                    'building_id': self.building.pk,
                                    'polygon_1000': [[150, 200], [450, 200], [450, 500], [150, 500]],
                                    'label_1000': [300, 350],
                                    'confidence': 0.97,
                                    'notes': 'Matched Block 1 corner wing',
                                }]
                            })
                        }]
                    }
                }]
            },
        )
        self.client.force_login(self.company_a)
        with override_settings(GEMINI_API_KEY='fake-gemini-key'):
            with patch('explorer.services.ai_vision.httpx.post', return_value=fake_match_resp):
                resp = self.client.post(reverse('explorer:complex_studio', args=[cx.pk]), {'action': 'ai_detect_blocks'})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['saved'], 1)
        hs = ComplexBuildingHotspot.objects.get(complex_explorer=cx, building=self.building)
        self.assertEqual(hs.ai_confidence, 0.97)
        self.assertIn('Block 1', hs.ai_notes)

    def test_v2_ai_sunset_night_relighting_generation_and_payload(self):
        self.building.refresh_from_db()
        exp = BuildingExplorer.objects.create(building=self.building, is_published=True, atmosphere_enabled=True)
        exp.hero_render.save('hero.png', SimpleUploadedFile('hero.png', _make_png_bytes(800, 600), content_type='image/png'))
        exp.hero_width = 800
        exp.hero_height = 600
        exp.save()

        sunset_b64 = __import__('base64').b64encode(_make_png_bytes(400, 300, (90, 140, 210))).decode('ascii')
        night_b64 = __import__('base64').b64encode(_make_png_bytes(400, 300, (30, 40, 80))).decode('ascii')

        def _fake_img_post(url, **kwargs):
            prompt_txt = kwargs['json']['contents'][0]['parts'][0]['text']
            b64 = sunset_b64 if 'SUNSET' in prompt_txt else night_b64
            return SimpleNamespace(
                status_code=200,
                text='ok',
                json=lambda: {'candidates': [{'content': {'parts': [{'inlineData': {'mimeType': 'image/png', 'data': b64}}]}}]},
            )

        self.client.force_login(self.company_a)
        with override_settings(GEMINI_API_KEY='fake-gemini-key', GEMINI_IMAGE_MODEL='gemini-3.1-flash-image'):
            with patch('explorer.services.ai_vision.httpx.post', side_effect=_fake_img_post):
                resp = self.client.post(
                    reverse('explorer:building_studio', args=[self.building.pk]),
                    {'action': 'generate_atmosphere'},
                )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['generated'], ['sunset', 'night'])
        self.assertTrue(body['sunset_url'])
        self.assertTrue(body['night_url'])

        pres_html = self.client.get(reverse('explorer:building_view', args=[self.building.pk])).content.decode('utf-8')
        self.assertIn('sunset_render_url', pres_html)
        self.assertIn('night_render_url', pres_html)
        self.assertIn(f'b{self.building.pk}_hero_sunset.jpg', pres_html)
        self.assertIn('Back to Exterior View', pres_html)

    def test_per_view_floor_bands_are_isolated_from_main_render(self):
        from django.core.files.storage import default_storage
        from explorer.views import serialize_building_payload

        hero_bytes = _make_png_bytes(800, 600, (120, 150, 200))
        exp = BuildingExplorer.objects.create(building=self.building, is_published=True)
        exp.hero_render.save('hero.png', SimpleUploadedFile('hero.png', hero_bytes, content_type='image/png'))
        dup_path = default_storage.save('explorer/renders/dup_view.png', SimpleUploadedFile('d.png', hero_bytes))
        v2_path = default_storage.save('explorer/renders/v2.png', SimpleUploadedFile('v2.png', _make_png_bytes(700, 500, (200, 100, 90))))
        v3_path = default_storage.save('explorer/renders/v3.png', SimpleUploadedFile('v3.png', _make_png_bytes(700, 500, (90, 200, 100))))
        exp.extra_renders = [
            {'path': dup_path, 'label': 'View 1 (p.8)', 'width': 800, 'height': 600, 'sky_score': 5.0},
            {'path': v2_path, 'label': 'View 2 (p.9)', 'width': 700, 'height': 500, 'sky_score': 5.0},
            {'path': v3_path, 'label': 'View 3 (p.10)', 'width': 700, 'height': 500, 'sky_score': 5.0},
        ]
        exp.save()
        for n in (1, 2, 3):
            FloorExplorer.objects.create(
                building_explorer=exp, floor_number=n,
                facade_polygon=[[50, 10 * n], [90, 10 * n], [90, 10 * n + 8], [50, 10 * n + 8]],
            )

        # Before any mapping: byte-identical angle is dropped, others carry NO floor shapes.
        payload = serialize_building_payload(exp)
        angles = payload['building']['extra_renders']
        self.assertEqual([a['label'] for a in angles], ['View 2', 'View 3'])
        self.assertTrue(all(a['floors'] == {} for a in angles))

        # Save View 2 bands: stored per view, Main polygons untouched, View 3 stays unmapped.
        self.client.force_login(self.company_a)
        studio_url = reverse('explorer:building_studio', args=[self.building.pk])
        view2_poly = [[5, 20], [45, 22], [45, 30], [5, 28]]
        resp = self.client.post(studio_url, {
            'action': 'save_view_bands',
            'view_path': v2_path,
            'facade_bands_json': json.dumps({'floors': {'1': view2_poly, '2': 'garbage'}}),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['updated'], 1)
        bad = self.client.post(studio_url, {'action': 'save_view_bands', 'view_path': 'explorer/renders/nope.png', 'facade_bands_json': '{}'})
        self.assertEqual(bad.status_code, 400)

        exp.refresh_from_db()
        angles = serialize_building_payload(exp)['building']['extra_renders']
        self.assertEqual(angles[0]['floors'], {'1': view2_poly})
        self.assertEqual(angles[1]['floors'], {})
        self.assertEqual(FloorExplorer.objects.get(building_explorer=exp, floor_number=1).facade_polygon[0], [50, 10])

        # AI detection for one view only writes that view's overlay.
        fake_faces = {'faces': [{'tl': [10, 20], 'tr': [60, 22], 'br': [60, 70], 'bl': [10, 68]}], 'camera_view': 'x', 'notes': ''}
        with patch('explorer.services.spatial_matcher.ai_vision.detect_facade_and_faces_with_ai', return_value=fake_faces):
            ai = self.client.post(studio_url, {'action': 'ai_analyze_facade', 'view_path': v3_path})
        self.assertEqual(ai.status_code, 200)
        self.assertEqual(set(ai.json()['floors'].keys()), {'1', '2', '3'})
        exp.refresh_from_db()
        self.assertIn(v3_path, exp.view_overlays)
        self.assertEqual(FloorExplorer.objects.get(building_explorer=exp, floor_number=1).facade_polygon[0], [50, 10])

        # Studio exposes the per-angle data and tabs.
        html = self.client.get(studio_url).content.decode('utf-8')
        self.assertIn('switchView', html)
        # Presentation never reads main-view shapes for other angles.
        pres = self.client.get(reverse('explorer:building_view', args=[self.building.pk])).content.decode('utf-8')
        self.assertIn('floorPoly(fl)', pres)
        self.assertIn('activeViewSelectable', pres)

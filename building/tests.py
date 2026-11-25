import json
from datetime import date
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from building.models import Building, Apartment
from contract.models import Contract
from users.models import CustomUser, CompanyProfile, Role, StaffProfile


class BuildingAndInventoryTests(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.company_a = CustomUser.objects.create_user(
            phone_number='+998902110001', password='password123', full_name='Builder A', is_company=True
        )
        CompanyProfile.objects.create(user=self.company_a, company_name='Builder A LLC')

        self.company_b = CustomUser.objects.create_user(
            phone_number='+998902110002', password='password123', full_name='Builder B', is_company=True
        )
        CompanyProfile.objects.create(user=self.company_b, company_name='Builder B LLC')

        self.customer = CustomUser.objects.create_user(
            phone_number='+998902110003', password='password123', full_name='Buyer One', is_customer=True
        )
        self.readonly_role = Role.objects.create(
            company=self.company_a, name='Viewer', permissions=['view_buildings']
        )
        self.staff_readonly = CustomUser.objects.create_user(
            phone_number='+998902110004', password='password123', full_name='Viewer Staff', is_staff_member=True
        )
        StaffProfile.objects.create(user=self.staff_readonly, company=self.company_a, role=self.readonly_role)

    def test_building_auto_grid_generation_and_matrix_counts(self):
        self.client.force_login(self.company_a)
        resp = self.client.post(reverse('building:create'), {
            'name': 'Navoi Residency',
            'block_number': 'A',
            'address': 'Tashkent',
            'floor_count': 3,
            'entrance_count': 2,
            'apartments_per_floor': 4,
        })
        building = Building.objects.get(company=self.company_a, name='Navoi Residency')
        self.assertRedirects(resp, reverse('building:matrix', args=[building.pk]))
        self.assertEqual(building.apartment_count, 24)
        self.assertEqual(building.apartments.count(), 24)

        # Add archived (is_real=False) + RESERVED + SOLD units and check matrix counts
        apt_first = building.apartments.order_by('id').first()
        apt_first.status = 'RESERVED'
        apt_first.save()
        Apartment.objects.create(
            building=building, apartment_number='999', floor_number=1, entrance_number=1,
            total_area=Decimal('50.00'), living_area=Decimal('40.00'), status='SOLD', is_real=False
        )

        m_resp = self.client.get(reverse('building:matrix', args=[building.pk]))
        self.assertEqual(m_resp.status_code, 200)
        self.assertEqual(m_resp.context['available_count'], 23)
        self.assertEqual(m_resp.context['reserved_count'], 1)
        self.assertEqual(m_resp.context['sold_count'], 0)

        # Cross-company isolation
        self.client.force_login(self.company_b)
        other_resp = self.client.get(reverse('building:matrix', args=[building.pk]))
        self.assertEqual(other_resp.status_code, 302)

    def test_building_create_with_custom_json_and_malformed_fallback(self):
        self.client.force_login(self.company_a)

        custom_json = json.dumps([
            {'Apartment Number': '101', 'Floor Number': 1, 'Entrance Number': 1, 'Rooms Count': 3, 'Total Area (m2)': '85.50', 'Living Area (m2)': '60.00', 'Balcony Area (m2)': '5.50'},
            {'Apartment Number': '102', 'Floor Number': 1, 'Entrance Number': 1, 'Rooms Count': 2, 'Total Area (m2)': '62.00', 'Living Area (m2)': '45.00', 'Balcony Area (m2)': '3.00'},
        ])
        self.client.post(reverse('building:create'), {
            'name': 'Custom JSON Block',
            'floor_count': 1,
            'entrance_count': 1,
            'apartments_per_floor': 2,
            'apartments_json': custom_json,
        })
        b_custom = Building.objects.get(name='Custom JSON Block')
        self.assertEqual(b_custom.apartments.count(), 2)
        self.assertEqual(b_custom.apartments.get(apartment_number='101').total_area, Decimal('85.50'))

        # Malformed JSON falls back to auto grid cleanly without 500 error
        self.client.post(reverse('building:create'), {
            'name': 'Fallback Block',
            'floor_count': 2,
            'entrance_count': 1,
            'apartments_per_floor': 2,
            'apartments_json': '{broken json',
        })
        b_fb = Building.objects.get(name='Fallback Block')
        self.assertEqual(b_fb.apartments.count(), 4)

    def test_apartment_update_available_vs_sold_immutability_and_permissions(self):
        building = Building.objects.create(company=self.company_a, name='Test Tower', floor_count=1, entrance_count=1, apartments_per_floor=2)
        apt_avail = Apartment.objects.create(
            building=building, apartment_number='1', floor_number=1, entrance_number=1,
            total_area=Decimal('50.00'), living_area=Decimal('38.00'), status='AVAILABLE'
        )
        apt_sold = Apartment.objects.create(
            building=building, apartment_number='2', floor_number=1, entrance_number=1,
            total_area=Decimal('70.00'), living_area=Decimal('52.00'), status='SOLD'
        )
        contract = Contract.objects.create(
            apartment=apt_sold, customer=self.customer, company=self.company_a,
            contract_id=777, contract_date=date(2026, 11, 1), price_per_square=Decimal('10000000.00'),
            payment_months=12
        )

        # Customer gets 404 on internal apartment modal
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse('building:apartment_update', args=[apt_avail.pk])).status_code, 404)

        # Readonly staff can view modal (GET) but cannot POST edit_buildings
        self.client.force_login(self.staff_readonly)
        self.assertEqual(self.client.get(reverse('building:apartment_update', args=[apt_avail.pk]), HTTP_HX_REQUEST='true').status_code, 200)
        deny_post = self.client.post(reverse('building:apartment_update', args=[apt_avail.pk]), {
            'living_room_count': 2, 'total_area': '55.00', 'living_area': '40.00', 'balcony_area': '0.00', 'status': 'AVAILABLE'
        })
        self.assertNotEqual(deny_post.status_code, 200)
        apt_avail.refresh_from_db()
        self.assertEqual(apt_avail.total_area, Decimal('50.00'))

        # Company admin can update AVAILABLE apartment
        self.client.force_login(self.company_a)
        ok_post = self.client.post(reverse('building:apartment_update', args=[apt_avail.pk]), {
            'living_room_count': 2, 'total_area': '58.00', 'living_area': '44.00', 'balcony_area': '2.00', 'status': 'RESERVED'
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(ok_post.status_code, 200)
        apt_avail.refresh_from_db()
        self.assertEqual(apt_avail.total_area, Decimal('58.00'))
        self.assertEqual(apt_avail.status, 'RESERVED')

        # SOLD apartment modal shows custom contract_id #777 and blocks modifications
        sold_get = self.client.get(reverse('building:apartment_update', args=[apt_sold.pk]), HTTP_HX_REQUEST='true')
        self.assertContains(sold_get, f'#{contract.contract_id}')

        self.client.post(reverse('building:apartment_update', args=[apt_sold.pk]), {
            'living_room_count': 1, 'total_area': '10.00', 'living_area': '10.00', 'balcony_area': '0.00', 'status': 'AVAILABLE'
        }, HTTP_HX_REQUEST='true')
        apt_sold.refresh_from_db()
        self.assertEqual(apt_sold.total_area, Decimal('70.00'))
        self.assertEqual(apt_sold.status, 'SOLD')

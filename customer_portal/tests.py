from datetime import date, datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from building.models import Building, Apartment
from contract.models import Contract, PaymentLog
from users.models import CustomUser, CompanyProfile


class CustomerPortalTests(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.company = CustomUser.objects.create_user(
            phone_number='+998904000001', password='password123', full_name='Dev Co', is_company=True
        )
        CompanyProfile.objects.create(user=self.company, company_name='Dev Co LLC')

        self.customer_a = CustomUser.objects.create_user(
            phone_number='+998904000002', password='password123', full_name='Customer A', is_customer=True
        )
        self.customer_b = CustomUser.objects.create_user(
            phone_number='+998904000003', password='password123', full_name='Customer B', is_customer=True
        )

        bld = Building.objects.create(company=self.company, name='Portal Tower', floor_count=2, entrance_count=1, apartments_per_floor=2)
        apt_a = Apartment.objects.create(
            building=bld, apartment_number='10', floor_number=1, entrance_number=1,
            total_area=Decimal('50.00'), living_area=Decimal('40.00'), status='SOLD'
        )
        apt_b = Apartment.objects.create(
            building=bld, apartment_number='20', floor_number=2, entrance_number=1,
            total_area=Decimal('60.00'), living_area=Decimal('48.00'), status='SOLD'
        )

        self.contract_a = Contract.objects.create(
            apartment=apt_a, customer=self.customer_a, company=self.company,
            contract_id=301, contract_date=date(2026, 10, 1), price_per_square=Decimal('1000000.00'),
            down_payment_amount=Decimal('10000000.00'), payment_months=4
        )
        PaymentLog.objects.create(
            contract=self.contract_a, amount=Decimal('10000000.00'),
            payment_type='CASH', date_paid=timezone.make_aware(datetime(2026, 10, 1, 12, 0))
        )
        self.contract_b = Contract.objects.create(
            apartment=apt_b, customer=self.customer_b, company=self.company,
            contract_id=302, contract_date=date(2026, 10, 1), price_per_square=Decimal('1000000.00'),
            payment_months=6
        )

    def test_customer_views_own_contracts_and_cannot_view_others(self):
        self.client.force_login(self.customer_a)

        home_resp = self.client.get(reverse('customer_portal:home'))
        self.assertEqual(home_resp.status_code, 200)
        self.assertIn(self.contract_a, home_resp.context['contracts'])
        self.assertNotIn(self.contract_b, home_resp.context['contracts'])

        detail_resp = self.client.get(reverse('customer_portal:contract_detail', args=[self.contract_a.pk]))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertEqual(detail_resp.context['total_paid'], Decimal('10000000.00'))
        self.assertEqual(detail_resp.context['total_remaining_debt'], Decimal('40000000.00'))

        # Customer A gets 404 for Customer B's contract
        other_resp = self.client.get(reverse('customer_portal:contract_detail', args=[self.contract_b.pk]))
        self.assertEqual(other_resp.status_code, 404)

    def test_company_user_redirected_from_customer_portal(self):
        self.client.force_login(self.company)
        self.assertRedirects(self.client.get(reverse('customer_portal:home')), reverse('dashboard:home'), fetch_redirect_response=False)
        self.assertRedirects(
            self.client.get(reverse('customer_portal:contract_detail', args=[self.contract_a.pk])),
            reverse('dashboard:home'),
            fetch_redirect_response=False,
        )

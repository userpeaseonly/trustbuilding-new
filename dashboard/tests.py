import datetime
from datetime import date, time
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from building.models import Building, Apartment
from contract.models import Contract, PaymentLog
from dashboard.models import DashboardSettings
from dashboard.templatetags.dashboard_tags import formatted_amount, get_item, uzs
from dashboard.templatetags.name_tags import short_name
from users.models import CustomUser, CompanyProfile, SMSLog


class DashboardAndTemplateTagsTests(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.company = CustomUser.objects.create_user(
            phone_number='+998909100001', password='password123', full_name='Dash Co', is_company=True
        )
        CompanyProfile.objects.create(user=self.company, company_name='Dash Co LLC')
        self.customer = CustomUser.objects.create_user(
            phone_number='+998909100002', password='password123', full_name='Buyer Dash', is_customer=True
        )

        bld = Building.objects.create(company=self.company, name='Dash Tower', floor_count=1, entrance_count=1, apartments_per_floor=2)
        apt1 = Apartment.objects.create(
            building=bld, apartment_number='1', floor_number=1, entrance_number=1,
            total_area=Decimal('50.00'), living_area=Decimal('40.00'), status='SOLD'
        )
        Apartment.objects.create(
            building=bld, apartment_number='2', floor_number=1, entrance_number=1,
            total_area=Decimal('50.00'), living_area=Decimal('40.00'), status='AVAILABLE'
        )

        today = timezone.localdate()
        self.contract = Contract.objects.create(
            apartment=apt1, customer=self.customer, company=self.company,
            contract_id=91, date_made=today, contract_date=today.replace(day=1),
            price_per_square=Decimal('1000000.00'), payment_months=2
        )
        PaymentLog.objects.create(
            contract=self.contract, amount=Decimal('15000000.00'), payment_type='CASH',
            date_paid=timezone.make_aware(datetime.datetime.combine(today, time(12, 0)))
        )
        SMSLog.objects.create(company=self.company, phone_number='998909100002', message='hi', status='SENT', cost=Decimal('160.00'), parts=1, operator='Beeline')

    def test_dashboard_home_excel_sms_usage_and_reconciliation(self):
        self.client.force_login(self.company)
        today = timezone.localdate()
        date_qs = f"?start_date={today.replace(day=1)}&end_date={today}"

        home_resp = self.client.get(reverse('dashboard:home') + date_qs)
        self.assertEqual(home_resp.status_code, 200)
        stats = home_resp.context['stats']
        self.assertEqual(stats['total_apartments'], 2)
        self.assertEqual(stats['sold_apartments'], 1)
        self.assertEqual(stats['inventory_sold_percent'], 50)
        self.assertEqual(stats['active_contracts_count'], 1)
        self.assertEqual(stats['monthly_revenue'], Decimal('15000000.00'))

        # Dashboard Excel export
        exp_resp = self.client.get(reverse('dashboard:home') + date_qs + '&export=excel')
        self.assertEqual(exp_resp.status_code, 200)
        self.assertIn('spreadsheetml', exp_resp['Content-Type'])

        # SMS Usage view
        sms_resp = self.client.get(reverse('dashboard:sms_usage'))
        self.assertEqual(sms_resp.status_code, 200)
        self.assertEqual(sms_resp.context['all_time_cost'], Decimal('160.00'))

        # Reconciliation math: begin + expected - paid == end
        rec_resp = self.client.get(reverse('dashboard:reconciliation') + date_qs)
        self.assertEqual(rec_resp.status_code, 200)
        row = rec_resp.context['report_data'][0]
        self.assertEqual(row['begin_balance'] + row['period_expected'] - row['period_paid'], row['end_balance'])

        rec_exp = self.client.get(reverse('dashboard:reconciliation') + date_qs + '&export=excel')
        self.assertEqual(rec_exp.status_code, 200)

    def test_dashboard_settings_singleton_and_template_tags(self):
        s1 = DashboardSettings.get_settings()
        s2 = DashboardSettings(schedule_start_time=time(9, 0))
        s2.save()
        self.assertEqual(DashboardSettings.objects.count(), 1)
        self.assertEqual(DashboardSettings.get_settings().pk, s1.pk)

        self.assertEqual(formatted_amount(1000000), '1 000 000')
        self.assertEqual(formatted_amount(Decimal('1250000.50')), '1 250 000.50')
        self.assertEqual(uzs(1000000), '1 000 000 UZS')
        self.assertEqual(get_item({'a': [1, 2]}, 'a'), [1, 2])
        self.assertEqual(short_name("Zuhra Yusupova"), "Z. Yusupova")
        self.assertEqual(short_name("Single"), "Single")

import datetime
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from bot.models import TelegramReportSubscriber
from bot.reports import compile_executive_report_data, build_morning_report_text, build_evening_report_text
from bot.services import handle_telegram_update, normalize_phone_number
from bot.tasks import send_morning_executive_reports, send_evening_executive_reports, send_instant_deal_alert
from building.models import Building, Apartment
from contract.models import Contract, PaymentLog
from finance.models import Wallet
from users.models import CustomUser, CompanyProfile, StaffProfile


class TelegramBotSuiteTests(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.company = CustomUser.objects.create_user(
            phone_number='+998909500001', password='password123', full_name='Bot Boss', is_company=True
        )
        CompanyProfile.objects.create(user=self.company, company_name='Bot Build LLC', director_name='Boss Man')

        self.cfo = CustomUser.objects.create_user(
            phone_number='+998909500002', password='password123', full_name='CFO User', is_staff_member=True
        )
        StaffProfile.objects.create(user=self.cfo, company=self.company, position='Moliya direktori (CFO)')

        self.sales = CustomUser.objects.create_user(
            phone_number='+998909500003', password='password123', full_name='Sales User', is_staff_member=True
        )
        StaffProfile.objects.create(user=self.sales, company=self.company, position='Sotuv menejeri')

        self.customer = CustomUser.objects.create_user(
            phone_number='+998909500004', password='password123', full_name='Buyer User', is_customer=True
        )

        bld = Building.objects.create(company=self.company, name='Bot Complex', floor_count=1, entrance_count=1, apartments_per_floor=2)
        apt = Apartment.objects.create(
            building=bld, apartment_number='7', floor_number=1, entrance_number=1,
            total_area=Decimal('50.00'), living_area=Decimal('40.00'), status='SOLD'
        )
        today = timezone.localdate()
        self.contract = Contract.objects.create(
            apartment=apt, customer=self.customer, company=self.company,
            contract_id=707, date_made=today, contract_date=today - timedelta(days=20),
            price_per_square=Decimal('1000000.00'), payment_months=2
        )
        rec = self.contract.payment_records.first()
        rec.due_date = today - timedelta(days=20)
        rec.save()

        PaymentLog.objects.create(
            contract=self.contract, amount=Decimal('3000000.00'), payment_type='CARD',
            date_paid=timezone.make_aware(datetime.datetime.combine(today, datetime.time(11, 0)))
        )
        Wallet.objects.create(company=self.company, name='USD Safe', wallet_type='CASH', currency='USD', initial_balance=Decimal('1000.00'))

    def test_executive_reports_compilation_and_formatting(self):
        data = compile_executive_report_data(self.company, target_date=timezone.localdate())
        self.assertEqual(data['sales_count'], 1)
        self.assertEqual(data['total_sales_uzs'], Decimal('50000000.00'))
        self.assertEqual(data['total_inflow'], Decimal('3000000.00'))
        self.assertEqual(data['card_inflow'], Decimal('3000000.00'))
        self.assertEqual(data['overdue_buyers_count'], 1)
        self.assertEqual(data['total_kassa_usd'], Decimal('1000.00'))

        morning_full = build_morning_report_text(data, report_level='FULL_EXECUTIVE')
        self.assertIn('TONGI KASSA', morning_full)
        morning_sales = build_morning_report_text(data, report_level='SALES_ONLY')
        self.assertNotIn('TONGI KASSA', morning_sales)

        evening_fin = build_evening_report_text(data, report_level='FINANCE_ONLY')
        self.assertNotIn('BUGUNGI SAVDO', evening_fin)
        self.assertIn('BUGUN YIG\'ILGAN TUSHUM', evening_fin)

    @patch('bot.services.send_telegram_message', return_value=True)
    def test_contact_verification_commands_and_webhook(self, mock_send):
        self.assertEqual(normalize_phone_number('901234567'), '+998901234567')

        # 1. Verify CEO, CFO, Sales, Customer, Unknown
        handle_telegram_update({'message': {'chat': {'id': 1001}, 'from': {'username': 'ceo'}, 'contact': {'phone_number': '+998909500001'}}})
        handle_telegram_update({'message': {'chat': {'id': 1002}, 'from': {'username': 'cfo'}, 'contact': {'phone_number': '998909500002'}}})
        handle_telegram_update({'message': {'chat': {'id': 1003}, 'from': {'username': 'sls'}, 'contact': {'phone_number': '909500003'}}})
        handle_telegram_update({'message': {'chat': {'id': 1004}, 'from': {'username': 'buy'}, 'contact': {'phone_number': '+998909500004'}}})
        handle_telegram_update({'message': {'chat': {'id': 1005}, 'from': {'username': 'unk'}, 'contact': {'phone_number': '+998909999999'}}})

        self.assertEqual(TelegramReportSubscriber.objects.get(chat_id=1001).report_level, 'FULL_EXECUTIVE')
        self.assertEqual(TelegramReportSubscriber.objects.get(chat_id=1002).report_level, 'FINANCE_ONLY')
        self.assertEqual(TelegramReportSubscriber.objects.get(chat_id=1003).report_level, 'SALES_ONLY')
        self.assertFalse(TelegramReportSubscriber.objects.filter(chat_id__in=[1004, 1005]).exists())

        # 2. Interactive commands
        handle_telegram_update({'message': {'chat': {'id': 9999}, 'text': '/start'}})
        handle_telegram_update({'message': {'chat': {'id': 1001}, 'text': '/today'}})
        handle_telegram_update({'message': {'chat': {'id': 1001}, 'text': '/kassa'}})
        handle_telegram_update({'message': {'chat': {'id': 1003}, 'text': '/kassa'}})  # Restricted for SALES_ONLY
        self.assertIn('cheklangan', mock_send.call_args[0][1])
        handle_telegram_update({'message': {'chat': {'id': 1001}, 'text': '/qarzdorlar'}})
        handle_telegram_update({'message': {'chat': {'id': 1001}, 'text': '/info'}})

        # 3. Webhook HTTP endpoint
        self.assertEqual(self.client.get(reverse('bot:webhook')).status_code, 405)
        self.assertEqual(self.client.post(reverse('bot:webhook'), data='{bad', content_type='application/json').status_code, 400)
        ok = self.client.post(
            reverse('bot:webhook'),
            data=json.dumps({'message': {'chat': {'id': 1001}, 'text': '/today'}}),
            content_type='application/json'
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json(), {'status': 'ok'})

    @patch('bot.tasks.send_telegram_message', return_value=True)
    def test_celery_report_and_instant_deal_alert_tasks(self, mock_send):
        TelegramReportSubscriber.objects.create(
            company=self.company, user=self.company, chat_id=2001, full_name='CEO',
            report_level='FULL_EXECUTIVE', receive_morning_report=True, receive_evening_report=True, receive_sale_alerts=True
        )
        self.assertIn('1/1', send_morning_executive_reports())
        self.assertIn('1/1', send_evening_executive_reports())
        alert_res = send_instant_deal_alert(self.contract.pk)
        self.assertEqual(alert_res, 'Deal alert sent to 1 subscribers.')
        self.assertIn('№707', mock_send.call_args[0][1])
        self.assertIn('50 000 000 UZS', mock_send.call_args[0][1])

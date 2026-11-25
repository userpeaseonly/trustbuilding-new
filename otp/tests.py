from datetime import timedelta, date
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from otp.models import OTPToken
from otp.services import EskizSMS
from otp.transliteration import (
    cyrillic_to_latin,
    format_sms_amount,
    build_overdue_sms,
    build_upcoming_reminder_sms,
    build_termination_otp_sms,
    build_login_otp_sms,
)
from users.models import CustomUser, SMSLog


class OtpTransliterationAndSmsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_cyrillic_to_latin_pure_gsm7(self):
        text = "Алишер Ўғли Ғани Қосим Ҳамид — ‘тест’ `"
        out = cyrillic_to_latin(text)
        self.assertIn("O'g'li", out)
        self.assertIn("G'ani", out)
        self.assertIn("Qosim", out)
        self.assertIn("Hamid", out)
        self.assertNotIn("‘", out)
        self.assertNotIn("’", out)
        self.assertNotIn("`", out)

        sms_text = build_overdue_sms("Алишер Қосимов", 105, date(2026, 11, 25), 5825000)
        self.assertIn("No105", sms_text)
        self.assertIn("25.11.2026", sms_text)
        self.assertIn("5 825 000", sms_text)
        self.assertTrue(all(ord(c) <= 127 for c in sms_text))

        self.assertEqual(format_sms_amount(1250000), "1 250 000")
        self.assertIn("No42", build_upcoming_reminder_sms(42, date(2026, 12, 1), 3000000))
        self.assertEqual(
            build_termination_otp_sms(105, "654321"),
            "TrustBuilding: No105 shartnomani bekor qilish uchun tasdiqlash kodi: 654321"
        )
        self.assertEqual(
            build_login_otp_sms("123456"),
            "TrustBuilding: Tizimga kirish uchun tasdiqlash kodi: 123456"
        )

    def test_calculate_sms_cost_operators_and_parts(self):
        self.assertEqual(EskizSMS.calculate_sms_cost('998971234567', 'Hello'), (170, 1, 'Mobiuz'))
        self.assertEqual(EskizSMS.calculate_sms_cost('998901234567', 'Hello'), (160, 1, 'Beeline'))
        self.assertEqual(EskizSMS.calculate_sms_cost('998931234567', 'Hello'), (160, 1, 'Ucell'))
        self.assertEqual(EskizSMS.calculate_sms_cost('998991234567', 'Hello'), (145, 1, 'Uzmobile'))
        self.assertEqual(EskizSMS.calculate_sms_cost('998331234567', 'Hello'), (95, 1, 'Humans'))
        self.assertEqual(EskizSMS.calculate_sms_cost('998981234567', 'Hello'), (110, 1, 'Perfectum'))

        # GSM-7 boundary: 160 chars = 1 part, 161 chars = 2 parts
        self.assertEqual(EskizSMS.calculate_sms_cost('998901234567', 'a' * 160)[1], 1)
        self.assertEqual(EskizSMS.calculate_sms_cost('998901234567', 'a' * 161)[1], 2)
        # UCS-2 boundary: 70 chars = 1 part, 71 chars = 2 parts
        self.assertEqual(EskizSMS.calculate_sms_cost('998901234567', 'А' * 70)[1], 1)
        self.assertEqual(EskizSMS.calculate_sms_cost('998901234567', 'А' * 71)[1], 2)

    @patch('otp.services.requests.post')
    def test_send_sms_mocked_and_logged(self, mock_post):
        auth_resp = MagicMock()
        auth_resp.json.return_value = {'data': {'token': 'mock-jwt-token'}}
        auth_resp.raise_for_status.return_value = None

        send_resp = MagicMock()
        send_resp.raise_for_status.return_value = None
        mock_post.side_effect = [auth_resp, send_resp]

        company = CustomUser.objects.create_user(phone_number='+998901112200', password='p', is_company=True)
        ok = EskizSMS.send_sms('+998901234567', 'TrustBuilding: Tizimga kirish uchun tasdiqlash kodi: 111222', company=company)
        self.assertTrue(ok)
        log = SMSLog.objects.get(company=company)
        self.assertEqual(log.status, 'SENT')
        self.assertEqual(log.operator, 'Beeline')
        self.assertEqual(log.cost, 160)


class OtpAuthFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(SERVER_NAME='localhost')
        self.company = CustomUser.objects.create_user(
            phone_number='+998903000001', password='p', full_name='Comp', is_company=True
        )
        self.customer = CustomUser.objects.create_user(
            phone_number='+998903000002', password='p', full_name='Cust', is_customer=True
        )
        self.inactive = CustomUser.objects.create_user(
            phone_number='+998903000003', password='p', full_name='Disabled', is_company=True, is_active=False
        )

    @patch('otp.views.EskizSMS.send_sms', return_value=True)
    def test_otp_request_and_verify_company_and_customer(self, mock_sms):
        # Unregistered & disabled phones rejected
        self.client.post(reverse('otp:request_otp'), {'phone_number': '+998909998877'})
        self.assertFalse(OTPToken.objects.exists())
        self.client.post(reverse('otp:request_otp'), {'phone_number': '+998903000003'})
        self.assertFalse(OTPToken.objects.exists())

        # Local 9-digit phone normalized to +998...
        req_resp = self.client.post(reverse('otp:request_otp'), {'phone_number': '90 300-00-02'})
        self.assertRedirects(req_resp, reverse('otp:verify_otp'))
        token = OTPToken.objects.get(phone_number='+998903000002')
        self.assertEqual(len(token.code), 6)
        mock_sms.assert_called_once()

        # Wrong OTP rejected
        bad_verify = self.client.post(reverse('otp:verify_otp'), {'code': '000000'})
        self.assertRedirects(bad_verify, reverse('otp:verify_otp'))

        # Valid OTP logs in customer & routes to customer_portal:home
        ok_verify = self.client.post(reverse('otp:verify_otp'), {'code': token.code})
        self.assertRedirects(ok_verify, reverse('customer_portal:home'), fetch_redirect_response=False)
        token.refresh_from_db()
        self.assertTrue(token.is_verified)

        # Rate limit blocks 4th request when 3 unexpired unverified tokens exist
        for _ in range(3):
            OTPToken.objects.create(phone_number='+998903000001', code='123456')
        self.client.logout()
        self.client.post(reverse('otp:request_otp'), {'phone_number': '+998903000001'})
        self.assertEqual(OTPToken.objects.filter(phone_number='+998903000001').count(), 3)

    def test_expired_otp_rejected(self):
        t = OTPToken.objects.create(
            phone_number='+998903000001',
            code='777888',
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        self.assertFalse(t.is_valid())
        session = self.client.session
        session['otp_phone_number'] = '+998903000001'
        session.save()
        resp = self.client.post(reverse('otp:verify_otp'), {'code': '777888'})
        self.assertRedirects(resp, reverse('otp:verify_otp'))
        self.assertNotIn('_auth_user_id', self.client.session)

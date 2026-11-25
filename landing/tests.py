from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from landing.models import LeadRequest


class LandingAndSubdomainRoutingTests(TestCase):
    def test_subdomain_routing_middleware(self):
        # about.trust-building.uz routes / directly to landing_home
        c_sub = Client(SERVER_NAME='about.trust-building.uz')
        resp_sub = c_sub.get('/')
        self.assertEqual(resp_sub.status_code, 200)
        self.assertEqual(resp_sub.context['demo_submit_url'], '/demo/')

        # about.localhost routes / directly to landing_home
        c_local_sub = Client(SERVER_NAME='about.localhost')
        resp_local_sub = c_local_sub.get('/')
        self.assertEqual(resp_local_sub.status_code, 200)
        self.assertEqual(resp_local_sub.context['demo_submit_url'], '/demo/')

        # Main domain / redirects to dashboard and serves landing at /about/
        c_main = Client(SERVER_NAME='trust-building.uz')
        self.assertEqual(c_main.get('/').status_code, 302)
        resp_about = c_main.get('/about/')
        self.assertEqual(resp_about.status_code, 200)
        self.assertEqual(resp_about.context['demo_submit_url'], '/about/demo/')

    def test_bilingual_language_switching(self):
        client = Client(SERVER_NAME='about.trust-building.uz')
        resp_ru = client.get('/?lang=ru')
        self.assertEqual(resp_ru.status_code, 200)
        self.assertEqual(resp_ru.context['current_lang'], 'ru')
        self.assertEqual(resp_ru.cookies['landing_lang'].value, 'ru')

        # Persisted in session
        resp_next = client.get('/')
        self.assertEqual(resp_next.context['current_lang'], 'ru')

    @patch('landing.services.send_telegram_message', return_value=True)
    @patch.dict('os.environ', {'TELEGRAM_LEAD_CHAT_ID': '123456789'})
    def test_submit_demo_request_json_and_validation(self, mock_tg):
        client = Client(SERVER_NAME='about.trust-building.uz')

        # Missing required fields -> 400 JSON
        bad = client.post(
            '/demo/',
            data='{"full_name": "", "phone_number": ""}',
            content_type='application/json'
        )
        self.assertEqual(bad.status_code, 400)
        self.assertFalse(bad.json()['success'])

        # Valid JSON lead submission
        ok = client.post(
            '/demo/',
            data='{"full_name": "Aziz Karimov", "phone_number": "+998901234567", "company_name": "BuildCo", "apartments_count": "200+", "lang": "uz"}',
            content_type='application/json',
            HTTP_X_FORWARDED_FOR='203.0.113.10, 10.0.0.1'
        )
        self.assertEqual(ok.status_code, 200)
        data = ok.json()
        self.assertTrue(data['success'])

        lead = LeadRequest.objects.get(pk=data['lead_id'])
        self.assertEqual(lead.full_name, 'Aziz Karimov')
        self.assertEqual(lead.ip_address, '203.0.113.10')
        self.assertTrue(lead.telegram_notified)
        mock_tg.assert_called_once()

    @patch('landing.services.send_telegram_message', return_value=False)
    def test_submit_demo_request_form_post(self, mock_tg):
        client = Client(SERVER_NAME='localhost')
        resp = client.post(reverse('landing:submit_demo'), {
            'full_name': 'Malika',
            'phone_number': '+998909876543',
            'company_name': 'Sky Tower',
        })
        self.assertRedirects(resp, reverse('landing:home'))
        self.assertTrue(LeadRequest.objects.filter(phone_number='+998909876543').exists())

from unittest.mock import patch
from django.conf import settings
from django.core import management
from django.db import DatabaseError
from django.template.loader import render_to_string
from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from users.models import CustomUser, CompanyProfile


class CoreApplicationTests(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.admin = CustomUser.objects.create_superuser(
            phone_number='+998900000001',
            password='adminpassword123',
            full_name='Super Admin',
        )
        self.company = CustomUser.objects.create_user(
            phone_number='+998901112233',
            password='password123',
            full_name='Demo Company Director',
            is_company=True,
        )
        CompanyProfile.objects.create(user=self.company, company_name='Demo Build LLC')

    def test_health_endpoint_ok_and_method_not_allowed(self):
        resp = self.client.get(reverse('health'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'status': 'ok'})
        self.assertEqual(resp.headers.get('Cache-Control'), 'no-store')

        post_resp = self.client.post(reverse('health'))
        self.assertEqual(post_resp.status_code, 405)

    def test_health_endpoint_returns_503_on_database_error(self):
        with patch('application.views.connection.cursor', side_effect=DatabaseError('db down')):
            resp = self.client.get(reverse('health'))
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json(), {'status': 'unavailable'})

    def test_root_redirect_and_schema_and_language_switch(self):
        root_resp = self.client.get(reverse('root'))
        self.assertEqual(root_resp.status_code, 302)
        self.assertEqual(root_resp.url, '/dashboard/')

        self.client.force_login(self.company)
        schema_resp = self.client.get(reverse('schema'))
        self.assertEqual(schema_resp.status_code, 200)

        lang_resp = self.client.post(reverse('set_language'), {'language': 'uz', 'next': '/about/'})
        self.assertEqual(lang_resp.status_code, 302)
        self.assertEqual(lang_resp.url, '/about/')

    def test_hijack_banner_disabled_and_header_button_only_for_hijacked(self):
        self.assertIsNone(settings.HIJACK_INSERT_BEFORE)

        # Normal user session should NOT see Stop impersonating button
        self.client.force_login(self.company)
        normal_resp = self.client.get(reverse('contract:list'))
        self.assertEqual(normal_resp.status_code, 200)
        self.assertNotContains(normal_resp, '/hijack/release/')
        self.assertNotContains(normal_resp, 'id="djhj"')

        # Simulated hijacked session SHOULD show header Stop impersonating button, no popup banner
        session = self.client.session
        session['hijack_history'] = [self.admin.pk]
        session.save()

        hijacked_resp = self.client.get(reverse('contract:list'))
        self.assertEqual(hijacked_resp.status_code, 200)
        self.assertContains(hijacked_resp, '/hijack/release/')
        self.assertContains(hijacked_resp, 'name="next" value="/admin/users/customuser/"')
        self.assertNotContains(hijacked_resp, 'id="djhj"')

        # Releasing hijack via header form returns superuser back to admin user list
        release_resp = self.client.post(
            reverse('hijack:release'),
            {'next': '/admin/users/customuser/'},
        )
        self.assertEqual(release_resp.status_code, 302)
        self.assertEqual(release_resp.url, '/admin/users/customuser/')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.admin.pk)

    def test_django_system_check(self):
        management.call_command('check')

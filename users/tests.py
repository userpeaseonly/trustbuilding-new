from django.test import TestCase, Client
from django.urls import reverse
from users.models import CustomUser, CompanyProfile, CustomerCompanyLink, Role, StaffProfile
from users.permissions import has_permission, get_safe_redirect_for_user
from contract.forms import ContractWizardForm
from users.forms import CustomerRegistrationForm


class MultiTenantCustomerIsolationTests(TestCase):
    def setUp(self):
        # Company A
        self.company_a = CustomUser.objects.create_user(
            phone_number='+998901111111',
            password='password123',
            full_name='Company A Director',
            is_company=True
        )
        CompanyProfile.objects.create(user=self.company_a, company_name='Company A LLC')

        # Company B
        self.company_b = CustomUser.objects.create_user(
            phone_number='+998902222222',
            password='password123',
            full_name='Company B Director',
            is_company=True
        )
        CompanyProfile.objects.create(user=self.company_b, company_name='Company B LLC')

        # Customer 1 (belonging to Company A)
        self.cust_1 = CustomUser.objects.create(
            phone_number='+998903333333',
            full_name='Customer Alpha',
            is_customer=True
        )
        CustomerCompanyLink.objects.create(customer=self.cust_1, company=self.company_a)

        # Customer 2 (belonging to Company B)
        self.cust_2 = CustomUser.objects.create(
            phone_number='+998904444444',
            full_name='Customer Beta',
            is_customer=True
        )
        CustomerCompanyLink.objects.create(customer=self.cust_2, company=self.company_b)

    def test_customer_list_isolation(self):
        client = Client(SERVER_NAME='localhost')

        # Test Company A sees ONLY Customer Alpha
        client.force_login(self.company_a)
        resp = client.get(reverse('users:customer_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Customer Alpha')
        self.assertNotContains(resp, 'Customer Beta')

        # Test Company B sees ONLY Customer Beta
        client.force_login(self.company_b)
        resp = client.get(reverse('users:customer_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Customer Beta')
        self.assertNotContains(resp, 'Customer Alpha')

    def test_search_customers_api_isolation(self):
        client = Client(SERVER_NAME='localhost')

        # Company A searches "Customer" -> sees Alpha, does NOT see Beta
        client.force_login(self.company_a)
        resp = client.get(reverse('contract:search_customers') + '?q=Customer')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Customer Alpha')
        self.assertNotContains(resp, 'Customer Beta')

        # Company B searches "Customer" -> sees Beta, does NOT see Alpha
        client.force_login(self.company_b)
        resp = client.get(reverse('contract:search_customers') + '?q=Customer')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Customer Beta')
        self.assertNotContains(resp, 'Customer Alpha')

    def test_contract_wizard_form_dropdown_isolation(self):
        form_a = ContractWizardForm(company=self.company_a)
        qs_a = form_a.fields['existing_customer'].queryset
        self.assertIn(self.cust_1, qs_a)
        self.assertNotIn(self.cust_2, qs_a)

        form_b = ContractWizardForm(company=self.company_b)
        qs_b = form_b.fields['existing_customer'].queryset
        self.assertIn(self.cust_2, qs_b)
        self.assertNotIn(self.cust_1, qs_b)

    def test_registration_form_isolation_and_federation(self):
        # Company A tries to register cust_1's phone again -> Must fail with duplicate error
        form_dup = CustomerRegistrationForm(
            {'phone_number': '+998903333333', 'full_name': 'Duplicate'},
            company=self.company_a
        )
        self.assertFalse(form_dup.is_valid())
        self.assertIn('phone_number', form_dup.errors)

        # Company B registers cust_1's phone -> Must SUCCEED and link cust_1 to Company B
        form_link = CustomerRegistrationForm(
            {'phone_number': '+998903333333', 'full_name': 'Customer Alpha in Company B'},
            company=self.company_b
        )
        self.assertTrue(form_link.is_valid(), form_link.errors)
        saved_cust = form_link.save()
        self.assertEqual(saved_cust.pk, self.cust_1.pk)

        # Cust 1 is now linked to both companies
        self.assertTrue(CustomerCompanyLink.objects.filter(customer=self.cust_1, company=self.company_a).exists())
        self.assertTrue(CustomerCompanyLink.objects.filter(customer=self.cust_1, company=self.company_b).exists())


class CustomUserModelAndAuthTests(TestCase):
    def test_user_manager_create_user_and_superuser(self):
        with self.assertRaises(ValueError):
            CustomUser.objects.create_user(phone_number='', password='pass123')

        user = CustomUser.objects.create_user(
            phone_number='+998905556677',
            password='pass123',
            full_name='Karimov Sardor Rustam o\'g\'li',
            is_customer=True,
        )
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password('pass123'))
        self.assertEqual(user.short_name, 'S.R. Karimov')

        su = CustomUser.objects.create_superuser(phone_number='+998905556688', password='adminpass123')
        self.assertTrue(su.is_staff)
        self.assertTrue(su.is_superuser)

    def test_short_name_variants(self):
        self.assertEqual(CustomUser(phone_number='+998901', full_name='').short_name, '')
        self.assertEqual(CustomUser(phone_number='+998902', full_name='Single').short_name, 'Single')
        self.assertEqual(CustomUser(phone_number='+998903', full_name='Karimova Nilufar Aziz qizi').short_name, 'N.A. Karimova')
        self.assertEqual(CustomUser(phone_number='+998904', full_name='Alimov Temur ўғли').short_name, 'T. Alimov')

    def test_login_and_logout_routing(self):
        company = CustomUser.objects.create_user(
            phone_number='+998907770001',
            password='password123',
            full_name='Director',
            is_company=True,
        )
        customer = CustomUser.objects.create_user(
            phone_number='+998907770002',
            password='password123',
            full_name='Buyer',
            is_customer=True,
        )
        client = Client(SERVER_NAME='localhost')

        # Invalid password fails gracefully
        bad_resp = client.post(reverse('users:login'), {'username': '+998907770001', 'password': 'wrong'})
        self.assertEqual(bad_resp.status_code, 200)

        # Customer logs in -> goes to customer_portal:home
        cust_resp = client.post(reverse('users:login'), {'username': '+998907770002', 'password': 'password123'})
        self.assertRedirects(cust_resp, reverse('customer_portal:home'), fetch_redirect_response=False)

        # Already-authenticated customer visiting login -> goes to customer_portal:home
        again_resp = client.get(reverse('users:login'))
        self.assertRedirects(again_resp, reverse('customer_portal:home'), fetch_redirect_response=False)

        # Logout redirects cleanly to OTP login
        out_resp = client.get(reverse('users:logout'))
        self.assertRedirects(out_resp, reverse('otp:request_otp'), fetch_redirect_response=False)

        # Company logs in -> goes to dashboard:home
        comp_resp = client.post(reverse('users:login'), {'username': '+998907770001', 'password': 'password123'})
        self.assertRedirects(comp_resp, reverse('dashboard:home'), fetch_redirect_response=False)


class PermissionsAndStaffCrudTests(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.company_a = CustomUser.objects.create_user(
            phone_number='+998901234001', password='password123', full_name='Company A', is_company=True
        )
        self.profile_a = CompanyProfile.objects.create(user=self.company_a, company_name='Comp A')

        self.company_b = CustomUser.objects.create_user(
            phone_number='+998901234002', password='password123', full_name='Company B', is_company=True
        )
        CompanyProfile.objects.create(user=self.company_b, company_name='Comp B')

        self.role_sales = Role.objects.create(
            company=self.company_a, name='Sales Only', permissions=['view_contracts']
        )
        self.role_empty = Role.objects.create(
            company=self.company_a, name='No Access', permissions=[]
        )

        self.staff_sales = CustomUser.objects.create_user(
            phone_number='+998901234003', password='password123', full_name='Sales Staff', is_staff_member=True
        )
        self.staff_sales_profile = StaffProfile.objects.create(
            user=self.staff_sales, company=self.company_a, position='Manager', role=self.role_sales
        )

        self.staff_empty = CustomUser.objects.create_user(
            phone_number='+998901234004', password='password123', full_name='Empty Staff', is_staff_member=True
        )
        self.staff_empty_profile = StaffProfile.objects.create(
            user=self.staff_empty, company=self.company_a, position='Trainee', role=self.role_empty
        )

        self.customer = CustomUser.objects.create_user(
            phone_number='+998901234005', password='password123', full_name='Plain Customer', is_customer=True
        )

    def test_permission_helpers_and_loop_free_redirects(self):
        self.assertTrue(has_permission(self.company_a, 'view_finance'))
        self.assertTrue(has_permission(self.staff_sales, 'view_contracts'))
        self.assertFalse(has_permission(self.staff_sales, 'view_reports'))
        self.assertFalse(has_permission(self.customer, 'view_contracts'))

        self.assertEqual(get_safe_redirect_for_user(self.customer), 'customer_portal:home')
        self.assertEqual(get_safe_redirect_for_user(self.staff_sales), 'contract:list')
        self.assertIsNone(get_safe_redirect_for_user(self.staff_empty))

        # Customer visiting dashboard goes directly to customer_portal:home (no redirect loop)
        self.client.force_login(self.customer)
        resp_cust = self.client.get(reverse('dashboard:home'))
        self.assertRedirects(resp_cust, reverse('customer_portal:home'), fetch_redirect_response=False)

        # Staff with view_contracts visiting dashboard is routed cleanly to contract:list
        self.client.force_login(self.staff_sales)
        resp_sales = self.client.get(reverse('dashboard:home'))
        self.assertRedirects(resp_sales, reverse('contract:list'), fetch_redirect_response=False)

        # Zero-permission staff visiting dashboard or contract list with self-referrer gets 403 (no loop)
        self.client.force_login(self.staff_empty)
        resp_empty = self.client.get(
            reverse('dashboard:home'),
            HTTP_REFERER=f"http://localhost{reverse('dashboard:home')}"
        )
        self.assertEqual(resp_empty.status_code, 403)

    def test_staff_and_role_crud_and_cross_tenant_isolation(self):
        self.client.force_login(self.company_a)

        # Create role with selected checkboxes
        r_create = self.client.post(reverse('users:role_create'), {
            'name': 'Accountant',
            'perm_view_finance': 'on',
            'perm_manage_finance': 'on',
        })
        self.assertEqual(r_create.status_code, 302)
        acct_role = Role.objects.get(company=self.company_a, name='Accountant')
        self.assertEqual(set(acct_role.permissions), {'view_finance', 'manage_finance'})

        # Duplicate role name handled cleanly without IntegrityError 500
        r_dup = self.client.post(reverse('users:role_create'), {'name': 'Accountant'})
        self.assertEqual(r_dup.status_code, 200)

        # Deleting a role currently assigned to staff triggers ProtectedError handler cleanly
        r_del_protected = self.client.post(reverse('users:role_delete', args=[self.role_sales.pk]))
        self.assertEqual(r_del_protected.status_code, 302)
        self.assertTrue(Role.objects.filter(pk=self.role_sales.pk).exists())

        # Create & delete unassigned role works
        r_del_ok = self.client.post(reverse('users:role_delete', args=[acct_role.pk]))
        self.assertEqual(r_del_ok.status_code, 302)
        self.assertFalse(Role.objects.filter(pk=acct_role.pk).exists())

        # Create staff member via staff_list
        s_create = self.client.post(reverse('users:staff_list'), {
            'phone_number': '+998908889900',
            'full_name': 'New Agent',
            'position': 'Agent',
            'role': self.role_sales.pk,
        })
        self.assertEqual(s_create.status_code, 302)
        new_sp = StaffProfile.objects.get(company=self.company_a, user__phone_number='+998908889900')

        # Edit staff member
        self.client.post(reverse('users:staff_edit', args=[new_sp.pk]), {
            'full_name': 'Updated Agent',
            'position': 'Senior Agent',
            'phone_number': '+998908889900',
            'role': '',
        })
        new_sp.refresh_from_db()
        self.assertEqual(new_sp.user.full_name, 'Updated Agent')
        self.assertIsNone(new_sp.role)

        # Toggle active & delete
        self.client.post(reverse('users:staff_toggle_active', args=[new_sp.pk]))
        new_sp.user.refresh_from_db()
        self.assertFalse(new_sp.user.is_active)

        self.client.post(reverse('users:staff_delete', args=[new_sp.pk]))
        self.assertFalse(StaffProfile.objects.filter(pk=new_sp.pk).exists())

        # Company B cannot edit Company A's staff or role
        self.client.force_login(self.company_b)
        self.assertEqual(self.client.post(reverse('users:staff_edit', args=[self.staff_sales_profile.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('users:role_edit', args=[self.role_sales.pk])).status_code, 404)

    def test_toggle_termination_otp_only_for_company_admin(self):
        self.assertTrue(self.profile_a.require_termination_otp)

        # Staff cannot change company OTP security setting
        self.client.force_login(self.staff_sales)
        self.client.post(reverse('users:toggle_termination_otp'), {'action': 'disable'})
        self.profile_a.refresh_from_db()
        self.assertTrue(self.profile_a.require_termination_otp)

        # Company admin disables then re-enables
        self.client.force_login(self.company_a)
        self.client.post(reverse('users:toggle_termination_otp'), {'action': 'disable'})
        self.profile_a.refresh_from_db()
        self.assertFalse(self.profile_a.require_termination_otp)

        self.client.post(reverse('users:toggle_termination_otp'), {'action': 'enable'})
        self.profile_a.refresh_from_db()
        self.assertTrue(self.profile_a.require_termination_otp)

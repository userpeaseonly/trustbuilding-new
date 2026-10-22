from django.test import TestCase, Client
from django.urls import reverse
from users.models import CustomUser, CompanyProfile, CustomerCompanyLink
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

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from building.models import Building, Apartment
from contract.models import Contract, PaymentLog, PaymentRecord
from finance.models import Wallet, ExpenseCategory, FinancialTransaction
from users.models import CustomUser, CompanyProfile, Role, StaffProfile


class FinanceLedgerAndViewsTests(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.company_a = CustomUser.objects.create_user(
            phone_number='+998908000001', password='password123', full_name='Fin Co A', is_company=True
        )
        CompanyProfile.objects.create(user=self.company_a, company_name='Finance Co A')

        self.company_b = CustomUser.objects.create_user(
            phone_number='+998908000002', password='password123', full_name='Fin Co B', is_company=True
        )
        CompanyProfile.objects.create(user=self.company_b, company_name='Finance Co B')

        self.customer = CustomUser.objects.create_user(
            phone_number='+998908000003', password='password123', full_name='Fin Buyer', is_customer=True
        )

        role_view = Role.objects.create(company=self.company_a, name='Fin Viewer', permissions=['view_finance'])
        self.staff_view = CustomUser.objects.create_user(
            phone_number='+998908000004', password='password123', full_name='Viewer', is_staff_member=True
        )
        StaffProfile.objects.create(user=self.staff_view, company=self.company_a, role=role_view)

        self.bld = Building.objects.create(company=self.company_a, name='Fin Block', floor_count=2, entrance_count=1, apartments_per_floor=2)
        self.apt = Apartment.objects.create(
            building=self.bld, apartment_number='1', floor_number=1, entrance_number=1,
            total_area=Decimal('50.00'), living_area=Decimal('40.00'), status='SOLD'
        )
        self.contract = Contract.objects.create(
            apartment=self.apt, customer=self.customer, company=self.company_a,
            contract_id=515, contract_date=date(2026, 10, 1),
            price_per_square=Decimal('1000000.00'), payment_months=2
        )

    def test_payment_sync_and_wallet_balance_math(self):
        cash_w = Wallet.objects.create(company=self.company_a, name='Main Cash', wallet_type='CASH', currency='UZS', initial_balance=Decimal('1000000.00'))
        bank_w = Wallet.objects.create(company=self.company_a, name='Bank Account', wallet_type='BANK', currency='UZS', initial_balance=Decimal('0.00'))

        # Contract payment signal reflects inflow into matching CASH wallet
        p = PaymentLog.objects.create(contract=self.contract, amount=Decimal('5000000.00'), payment_type='CASH')
        self.assertEqual(cash_w.current_balance, Decimal('6000000.00'))

        # Updating PaymentLog updates existing linked transaction
        p.amount = Decimal('7000000.00')
        p.save()
        self.assertEqual(cash_w.current_balance, Decimal('8000000.00'))
        self.assertEqual(FinancialTransaction.objects.filter(payment_log=p).count(), 1)

        # Manual expense & transfer math
        FinancialTransaction.objects.create(
            company=self.company_a, transaction_type='EXPENSE', wallet=cash_w,
            amount=Decimal('1500000.00'), date=timezone.localdate(), description='Cement'
        )
        FinancialTransaction.objects.create(
            company=self.company_a, transaction_type='TRANSFER', wallet=cash_w,
            target_wallet=bank_w, amount=Decimal('2500000.00'), date=timezone.localdate(), description='Deposit'
        )
        self.assertEqual(cash_w.current_balance, Decimal('4000000.00'))
        self.assertEqual(bank_w.current_balance, Decimal('2500000.00'))

    def test_add_transaction_decimal_precision_validation_and_deletion_guards(self):
        cash_w = Wallet.objects.create(company=self.company_a, name='Cash', wallet_type='CASH', currency='UZS')
        bank_w = Wallet.objects.create(company=self.company_a, name='Bank', wallet_type='BANK', currency='UZS')
        cat = ExpenseCategory.objects.create(company=self.company_a, name='Materials', category_type='EXPENSE')

        self.client.force_login(self.company_a)

        # Large decimal amount must NOT lose precision via float()
        self.client.post(reverse('finance:add_transaction'), {
            'transaction_type': 'INCOME',
            'amount': '12345678901234.56',
            'wallet': cash_w.pk,
            'date': timezone.localdate().strftime('%Y-%m-%d'),
            'description': 'High precision test',
        })
        tx = FinancialTransaction.objects.get(company=self.company_a, description='High precision test')
        self.assertEqual(tx.amount, Decimal('12345678901234.56'))

        # Reject invalid amounts (0, negative, NaN, inf, non-numeric)
        for bad_amt in ('0', '-100', 'NaN', 'Infinity', 'abc'):
            self.client.post(reverse('finance:add_transaction'), {
                'transaction_type': 'EXPENSE', 'amount': bad_amt, 'wallet': cash_w.pk
            })
        self.assertEqual(FinancialTransaction.objects.filter(company=self.company_a, transaction_type='EXPENSE').count(), 0)

        # Same-wallet transfer rejected
        self.client.post(reverse('finance:add_transaction'), {
            'transaction_type': 'TRANSFER', 'amount': '500', 'wallet': cash_w.pk, 'target_wallet': cash_w.pk
        })
        self.assertEqual(FinancialTransaction.objects.filter(transaction_type='TRANSFER').count(), 0)

        # Valid expense & transfer
        self.client.post(reverse('finance:add_transaction'), {
            'transaction_type': 'EXPENSE', 'amount': '50000.00', 'wallet': cash_w.pk,
            'category': cat.pk, 'building': self.bld.pk, 'description': 'Bricks'
        })
        self.client.post(reverse('finance:add_transaction'), {
            'transaction_type': 'TRANSFER', 'amount': '100000', 'wallet': cash_w.pk, 'target_wallet': bank_w.pk
        })

        # Contract-synced tx cannot be deleted via finance:delete_transaction; manual tx CAN be deleted
        p = PaymentLog.objects.create(contract=self.contract, amount=Decimal('1000000.00'), payment_type='CASH')
        linked_tx = FinancialTransaction.objects.get(payment_log=p)
        self.client.post(reverse('finance:delete_transaction', args=[linked_tx.pk]))
        self.assertTrue(FinancialTransaction.objects.filter(pk=linked_tx.pk).exists())

        self.client.post(reverse('finance:delete_transaction', args=[tx.pk]))
        self.assertFalse(FinancialTransaction.objects.filter(pk=tx.pk).exists())

    def test_wallets_categories_and_duplicate_category_no_500(self):
        self.client.force_login(self.company_a)
        self.client.post(reverse('finance:manage_wallets'), {
            'name': 'USD Vault', 'wallet_type': 'CASH', 'currency': 'USD', 'initial_balance': '1500.75'
        })
        self.assertEqual(Wallet.objects.get(company=self.company_a, name='USD Vault').initial_balance, Decimal('1500.75'))

        # Invalid initial balance falls back cleanly to 0.00
        self.client.post(reverse('finance:manage_wallets'), {
            'name': 'Fallback Wallet', 'wallet_type': 'CASH', 'currency': 'UZS', 'initial_balance': 'NaN'
        })
        self.assertEqual(Wallet.objects.get(company=self.company_a, name='Fallback Wallet').initial_balance, Decimal('0.00'))

        # Duplicate category does NOT raise IntegrityError 500
        self.client.post(reverse('finance:manage_categories'), {'name': 'Unique Cat', 'category_type': 'EXPENSE'})
        dup_resp = self.client.post(reverse('finance:manage_categories'), {'name': 'Unique Cat', 'category_type': 'EXPENSE'})
        self.assertRedirects(dup_resp, reverse('finance:manage_categories'))
        self.assertEqual(ExpenseCategory.objects.filter(company=self.company_a, name='Unique Cat').count(), 1)

    @patch('finance.views.send_sms', return_value=True)
    def test_overview_tabs_excel_export_debtor_sms_and_permissions(self, mock_sms):
        today = timezone.localdate()
        rec = self.contract.payment_records.first()
        rec.due_date = today - timedelta(days=20)
        rec.save()

        self.client.force_login(self.company_a)
        for tab in ('cashflow', 'debtors', 'costing'):
            r = self.client.get(reverse('finance:overview') + f'?tab={tab}')
            self.assertEqual(r.status_code, 200)

        exp = self.client.get(reverse('finance:overview') + '?export=excel')
        self.assertEqual(exp.status_code, 200)
        self.assertIn('spreadsheetml', exp['Content-Type'])

        # Debtor reminder uses custom contract_id #515
        sms_resp = self.client.post(reverse('finance:send_debtor_reminder', args=[rec.pk]))
        self.assertRedirects(sms_resp, f"{reverse('finance:overview')}?tab=debtors")
        mock_sms.assert_called_once()
        self.assertIn('No515', mock_sms.call_args[0][1])

        # Permissions: customer redirected to portal; viewer-only staff cannot add/delete or send sms
        self.client.force_login(self.customer)
        self.assertRedirects(self.client.get(reverse('finance:overview')), reverse('customer_portal:home'), fetch_redirect_response=False)

        self.client.force_login(self.staff_view)
        self.assertEqual(self.client.get(reverse('finance:overview')).status_code, 200)
        self.assertEqual(self.client.post(reverse('finance:add_transaction'), {'amount': '100'}).status_code, 302)
        self.assertEqual(self.client.post(reverse('finance:send_debtor_reminder', args=[rec.pk])).status_code, 302)
        self.assertEqual(mock_sms.call_count, 1)

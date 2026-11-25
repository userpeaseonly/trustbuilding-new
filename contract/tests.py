import datetime
import io
import os
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from docx import Document
import openpyxl

from building.models import Building, Apartment
from contract.docx_generator import CustomDocxTemplate, build_contract_docx
from contract.forms import ContractWizardForm
from contract.models import (
    Contract,
    ContractTemplate,
    PaymentLog,
    PaymentRecord,
    TerminateContract,
    TerminateContractPayment,
)
from contract.tasks import process_daily_payment_reminders
from contract.utils.utils import amount_to_words_ru, convert_integer_to_words, number_to_words
from finance.models import FinancialTransaction, Wallet
from users.models import CompanyProfile, CustomUser, Role, StaffProfile


class ContractTestMixin:
    def _create_company_and_unit(self, suffix='1', area='60.00'):
        company = CustomUser.objects.create_user(
            phone_number=f'+9989050000{suffix}',
            password='password123',
            full_name=f'Company {suffix}',
            is_company=True,
        )
        CompanyProfile.objects.create(
            user=company,
            company_name=f'Developer {suffix} LLC',
            director_name='Aziz Rahimov',
            director_short_name='A. Rahimov',
            inn='301234567',
            address='Tashkent',
            require_termination_otp=False,
        )
        customer = CustomUser.objects.create_user(
            phone_number=f'+9989060000{suffix}',
            password='password123',
            full_name=f'Customer {suffix}',
            is_customer=True,
            passport_series='AA1234567',
            passport_jshshr='31204951820042',
        )
        building = Building.objects.create(
            company=company,
            name=f'Complex {suffix}',
            block_number='A',
            address='Chilonzor',
            floor_count=5,
            entrance_count=1,
            apartments_per_floor=4,
        )
        apt = Apartment.objects.create(
            building=building,
            apartment_number=f'1{suffix}',
            floor_number=2,
            entrance_number=1,
            living_room_count=2,
            total_area=Decimal(area),
            living_area=Decimal('45.00'),
            balcony_area=Decimal('5.00'),
        )
        return company, customer, building, apt


class ContractScheduleAndMathTests(ContractTestMixin, TestCase):
    def test_schedule_generation_variants_sum_to_total_amount(self):
        company, customer, building, apt = self._create_company_and_unit('01', area='50.00')

        # 1. Remainder tiyin allocation: 50 * 2,000,000 = 100,000,000 split across 3 months
        c1 = Contract.objects.create(
            apartment=apt,
            customer=customer,
            company=company,
            contract_id=101,
            contract_date=date(2026, 1, 15),
            price_per_square=Decimal('2000000.00'),
            down_payment_amount=Decimal('0.00'),
            last_payment_amount=Decimal('0.00'),
            payment_months=3,
        )
        self.assertEqual(c1.total_amount, Decimal('100000000.00'))
        recs1 = list(c1.payment_records.order_by('month_number'))
        self.assertEqual(len(recs1), 3)
        self.assertEqual(sum(r.plan_amount for r in recs1), c1.total_amount)
        self.assertEqual(recs1[-1].plan_amount, Decimal('33333333.34'))

        # 2. DP + intermediate months + LP with custom down_payment_date
        apt2 = Apartment.objects.create(
            building=building, apartment_number='20', floor_number=3, entrance_number=1,
            total_area=Decimal('60.00'), living_area=Decimal('48.00')
        )
        c2 = Contract.objects.create(
            apartment=apt2,
            customer=customer,
            company=company,
            contract_id=102,
            contract_date=date(2026, 2, 1),
            down_payment_date=date(2026, 1, 15),
            price_per_square=Decimal('1000000.00'),
            down_payment_amount=Decimal('10000000.00'),
            last_payment_amount=Decimal('14000000.00'),
            payment_months=3,
        )
        recs2 = list(c2.payment_records.order_by('month_number'))
        self.assertEqual(len(recs2), 5)  # 1 DP + 3 months + 1 LP
        self.assertEqual(recs2[0].due_date, date(2026, 1, 15))
        self.assertEqual(recs2[1].due_date, date(2026, 2, 1))
        self.assertEqual(recs2[4].plan_amount, Decimal('14000000.00'))
        self.assertEqual(sum(r.plan_amount for r in recs2), c2.total_amount)

        # 3. 0 payment months fallback
        apt3 = Apartment.objects.create(
            building=building, apartment_number='21', floor_number=3, entrance_number=1,
            total_area=Decimal('40.00'), living_area=Decimal('32.00')
        )
        c3 = Contract.objects.create(
            apartment=apt3,
            customer=customer,
            company=company,
            contract_id=103,
            contract_date=date(2026, 3, 1),
            price_per_square=Decimal('1000000.00'),
            payment_months=0,
        )
        recs3 = list(c3.payment_records.all())
        self.assertEqual(len(recs3), 1)
        self.assertEqual(recs3[0].plan_amount, Decimal('40000000.00'))

    def test_contract_id_unique_per_company_and_wizard_auto_increment(self):
        company_a, cust_a, _, apt_a = self._create_company_and_unit('02', area='50.00')
        company_b, cust_b, _, apt_b = self._create_company_and_unit('03', area='50.00')

        Contract.objects.create(
            apartment=apt_a, customer=cust_a, company=company_a, contract_id=500,
            contract_date=date(2026, 5, 1), price_per_square=Decimal('1000000.00'), payment_months=2
        )

        # Same contract_id in different company is allowed
        c_b = Contract.objects.create(
            apartment=apt_b, customer=cust_b, company=company_b, contract_id=500,
            contract_date=date(2026, 5, 1), price_per_square=Decimal('1000000.00'), payment_months=2
        )
        self.assertEqual(str(c_b), f"Contract #500 - {cust_b.full_name}")

        # Wizard initial auto-increments per company
        form_a = ContractWizardForm(company=company_a)
        self.assertEqual(form_a.initial['contract_id'], 501)

        # Duplicate contract_id inside same company raises IntegrityError
        with self.assertRaises(IntegrityError):
            Contract.objects.create(
                apartment=apt_a, customer=cust_a, company=company_a, contract_id=500,
                contract_date=date(2026, 5, 1), price_per_square=Decimal('1000000.00'), payment_months=2
            )

    def test_recalculate_debt_calendar_matching_overpayment_and_delete(self):
        company, customer, _, apt = self._create_company_and_unit('04', area='30.00')
        c = Contract.objects.create(
            apartment=apt,
            customer=customer,
            company=company,
            contract_id=201,
            contract_date=date(2026, 6, 1),
            price_per_square=Decimal('1000000.00'),
            payment_months=3,  # 10,000,000 per month: June, July, August
        )
        # Pay 12,000,000 in June (overpays June row by 2M) and 4,000,000 in July (partial)
        p1 = PaymentLog.objects.create(
            contract=c, amount=Decimal('12000000.00'), payment_type='CASH',
            date_paid=timezone.make_aware(datetime.datetime(2026, 6, 10, 12, 0))
        )
        p2 = PaymentLog.objects.create(
            contract=c, amount=Decimal('4000000.00'), payment_type='CARD',
            date_paid=timezone.make_aware(datetime.datetime(2026, 7, 10, 12, 0))
        )

        r1, r2, r3 = list(c.payment_records.order_by('month_number'))
        self.assertEqual(r1.paid_amount, Decimal('12000000.00'))
        self.assertEqual(r1.debt, Decimal('0.00'))
        self.assertEqual(r1.excess_amount, Decimal('2000000.00'))
        self.assertEqual(r1.status, 'PAID')

        self.assertEqual(r2.paid_amount, Decimal('4000000.00'))
        self.assertEqual(r2.debt, Decimal('6000000.00'))
        self.assertEqual(r2.excess_amount, Decimal('0.00'))
        self.assertEqual(r2.status, 'PARTIAL')

        for r in (r1, r2, r3):
            self.assertEqual(r.paid_amount, r.plan_amount - r.debt + r.excess_amount)

        self.assertEqual(c.total_paid, Decimal('16000000.00'))
        self.assertEqual(c.remaining_debt, Decimal('14000000.00'))
        self.assertEqual(c.paid_percentage, Decimal('53.3'))

        # Delete payment log -> debt recalculates cleanly back to plan_amount
        p2.delete()
        r2.refresh_from_db()
        self.assertEqual(r2.paid_amount, Decimal('0.00'))
        self.assertEqual(r2.debt, r2.plan_amount)


class ContractWorkflowsViewsTests(ContractTestMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(SERVER_NAME='localhost')
        self.company_a, self.customer_a, self.bld_a, self.apt_a = self._create_company_and_unit('05', area='50.00')
        self.company_b, self.customer_b, self.bld_b, self.apt_b = self._create_company_and_unit('06', area='50.00')

    def test_contract_wizard_create_payment_idempotency_and_receipt_isolation(self):
        with tempfile.TemporaryDirectory() as tmp_media, self.settings(MEDIA_ROOT=tmp_media):
            self.client.force_login(self.company_a)

            # Create contract with inline new customer
            create_resp = self.client.post(reverse('contract:create'), {
                'customer_mode': 'new',
                'new_customer_phone': '+998907778899',
                'new_customer_name': 'Rustam Karimov',
                'new_customer_passport_series': 'AD1112233',
                'new_customer_passport_jshshr': '31204951820099',
                'contract_id': 909,
                'apartment': self.apt_a.pk,
                'date_made': '01/11/2026',
                'contract_date': '01/11/2026',
                'price_per_square': '1000000.00',
                'down_payment_amount': '10000000.00',
                'last_payment_amount': '0.00',
                'payment_months': 4,
            })
            contract = Contract.objects.get(company=self.company_a, contract_id=909)
            self.assertRedirects(create_resp, reverse('contract:detail', args=[contract.pk]))
            self.apt_a.refresh_from_db()
            self.assertEqual(self.apt_a.status, 'SOLD')

            # Idempotency key deduplicates double-submit
            url = reverse('contract:process_payment', args=[contract.pk])
            r1 = self.client.post(url, {'amount': '5000000.00', 'payment_type': 'CARD', 'idempotency_key': 'idem-key-1'})
            r2 = self.client.post(url, {'amount': '5000000.00', 'payment_type': 'CARD', 'idempotency_key': 'idem-key-1'})
            self.assertEqual(PaymentLog.objects.filter(contract=contract).count(), 1)
            self.assertEqual(r1.url, r2.url)

            # 15-second debounce blocks accidental identical POST without idempotency key
            self.client.post(url, {'amount': '5000000.00', 'payment_type': 'CARD'})
            self.assertEqual(PaymentLog.objects.filter(contract=contract).count(), 1)

            # Invalid (zero) amount rejected
            self.client.post(url, {'amount': '0', 'payment_type': 'CASH'})
            self.assertEqual(PaymentLog.objects.filter(contract=contract).count(), 1)

            # Payment synced to Finance ledger automatically
            self.assertEqual(FinancialTransaction.objects.filter(contract=contract, amount=Decimal('5000000.00')).count(), 1)

            # Receipt access: Company A and owner Customer OK; Company B & Customer B get 404
            payment = PaymentLog.objects.get(contract=contract)
            receipt_url = reverse('contract:receipt', args=[payment.pk])
            ok_comp = self.client.get(receipt_url)
            self.assertEqual(ok_comp.status_code, 200)
            self.assertContains(ok_comp, '№909')
            self.assertContains(ok_comp, 'ПЛАСТИК')

            self.client.force_login(contract.customer)
            self.assertEqual(self.client.get(receipt_url).status_code, 200)

            self.client.force_login(self.company_b)
            self.assertEqual(self.client.get(receipt_url).status_code, 404)

            self.client.force_login(self.customer_b)
            self.assertEqual(self.client.get(receipt_url).status_code, 404)

    def test_contract_list_filtering_sorting_and_search_apis(self):
        c1 = Contract.objects.create(
            apartment=self.apt_a, customer=self.customer_a, company=self.company_a,
            contract_id=10, contract_date=date(2026, 1, 1), price_per_square=Decimal('1000000.00'), payment_months=2
        )
        apt2 = Apartment.objects.create(
            building=self.bld_a, apartment_number='99', floor_number=1, entrance_number=1,
            total_area=Decimal('80.00'), living_area=Decimal('60.00')
        )
        c2 = Contract.objects.create(
            apartment=apt2, customer=self.customer_a, company=self.company_a,
            contract_id=20, contract_date=date(2026, 1, 1), price_per_square=Decimal('1000000.00'), payment_months=2,
            status=Contract.STATUS_COMPLETED
        )

        self.client.force_login(self.company_a)
        for sort_key in ('newest', 'oldest', 'id_desc', 'id_asc', 'amount_desc', 'amount_asc'):
            resp = self.client.get(reverse('contract:list') + f'?sort={sort_key}&status=ACTIVE&has_debt=true&q=20')
            self.assertEqual(resp.status_code, 200)

        # Status filter isolates ACTIVE vs COMPLETED
        resp_comp = self.client.get(reverse('contract:list') + '?status=COMPLETED')
        self.assertEqual(list(resp_comp.context['page_obj']), [c2])

        # HTMX apartment search returns only AVAILABLE is_real=True units for company A
        self.assertEqual(self.client.get(reverse('contract:search_apartments') + '?q=99').status_code, 200)
        self.assertEqual(self.client.get(reverse('contract:quick_payment') + f'?customer={self.customer_a.pk}').status_code, 200)

    def test_excel_import_export_and_template(self):
        c = Contract.objects.create(
            apartment=self.apt_a, customer=self.customer_a, company=self.company_a,
            contract_id=305, contract_date=date(2026, 10, 1), price_per_square=Decimal('1000000.00'), payment_months=2
        )
        self.client.force_login(self.company_a)

        # Blank import template download
        tpl_resp = self.client.get(reverse('contract:download_import_template'))
        self.assertEqual(tpl_resp.status_code, 200)
        self.assertIn('spreadsheetml', tpl_resp['Content-Type'])

        # Import Excel payments
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['Sana (DD.MM.YYYY)', 'Summa', "To'lov turi"])
        ws.append(['01.10.2026', 15000000, 'Cash'])
        ws.append(['01.11.2026', 10000000, 'Card'])
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        upload = SimpleUploadedFile('payments.xlsx', bio.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        imp_resp = self.client.post(reverse('contract:import_payments', args=[c.pk]), {'file': upload})
        self.assertRedirects(imp_resp, reverse('contract:detail', args=[c.pk]))
        self.assertEqual(c.payment_logs.count(), 2)
        self.assertEqual(c.total_paid, Decimal('25000000.00'))

        # Re-importing once payments exist must be blocked
        bio.seek(0)
        upload2 = SimpleUploadedFile('payments2.xlsx', bio.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.client.post(reverse('contract:import_payments', args=[c.pk]), {'file': upload2})
        self.assertEqual(c.payment_logs.count(), 2)

        # Download payments Excel
        dl_resp = self.client.get(reverse('contract:download_payments', args=[c.pk]))
        self.assertEqual(dl_resp.status_code, 200)

    def test_docx_generation_immutability_and_words_utils(self):
        self.assertIn('бир миллион', convert_integer_to_words(1000000))
        self.assertIn('нол сўм', number_to_words(0))
        self.assertIn('Пять миллионов', amount_to_words_ru(5000000))
        self.assertIn('Две тысячи', amount_to_words_ru(2000))

        with tempfile.TemporaryDirectory() as tmp_media, self.settings(MEDIA_ROOT=tmp_media):
            # Build minimal docx template with fragmented XML & Russian quotes
            doc = Document()
            doc.add_paragraph('Contract № «Шартнома_рақами» — «ООО Пример» - {{ Xaridor_FIO }}')
            tbl = doc.add_table(rows=6, cols=4)
            tbl.rows[0].cells[1].text = 'Тўлов номи'
            tbl.rows[5].cells[1].text = 'Жами'
            bio = io.BytesIO()
            doc.save(bio)
            bio.seek(0)

            self.client.force_login(self.company_a)
            up = SimpleUploadedFile('tpl.docx', bio.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            self.client.post(reverse('contract:template_create'), {'name': 'Custom UZB', 'file': up, 'is_default': 'on'})
            tmpl = ContractTemplate.objects.get(company=self.company_a, name='Custom UZB')
            self.assertTrue(tmpl.is_default)

            # Verify patch_xml converts known chevron tag and leaves Russian quotes intact
            patcher = CustomDocxTemplate(tmpl.file.path)
            patched = patcher.patch_xml('«<w:t>Шартнома_рақами</w:t>» «ООО» {% tr for r in schedule %}')
            self.assertIn('{{ Шартнома_рақами }}', patched)
            self.assertIn('«ООО»', patched)
            self.assertIn('{%tr for', patched)

            c = Contract.objects.create(
                apartment=self.apt_a, customer=self.customer_a, company=self.company_a,
                contract_id=404, contract_date=date(2026, 8, 1), price_per_square=Decimal('1000000.00'),
                down_payment_amount=Decimal('5000000.00'), payment_months=2
            )
            path1 = build_contract_docx(c)
            self.assertTrue(path1 and os.path.exists(path1))
            mtime1 = os.path.getmtime(path1)

            # Without force_regenerate, cached file is returned untouched
            path2 = build_contract_docx(c, force_regenerate=False)
            self.assertEqual(path1, path2)
            self.assertEqual(os.path.getmtime(path2), mtime1)

            # force_regenerate rebuilds document
            dl_resp = self.client.get(reverse('contract:download_docx', args=[c.pk]))
            self.assertEqual(dl_resp.status_code, 200)
            self.assertIn('Shartnoma_404.docx', dl_resp['Content-Disposition'])
            if getattr(dl_resp, 'file_to_stream', None):
                dl_resp.file_to_stream.close()

            regen_resp = self.client.post(reverse('contract:regenerate_docx', args=[c.pk]))
            self.assertRedirects(regen_resp, reverse('contract:detail', args=[c.pk]))

            # Template delete & set default
            tmpl2 = ContractTemplate.objects.create(company=self.company_a, name='Second', file=tmpl.file)
            self.client.post(reverse('contract:template_set_default', args=[tmpl2.pk]))
            tmpl2.refresh_from_db()
            self.assertTrue(tmpl2.is_default)
            self.client.post(reverse('contract:template_delete', args=[tmpl.pk]))
            self.assertFalse(ContractTemplate.objects.filter(pk=tmpl.pk).exists())

    @patch('contract.views.send_sms', return_value=True)
    def test_termination_otp_direct_refund_and_custom_contract_id_display(self, mock_sms):
        c = Contract.objects.create(
            apartment=self.apt_a, customer=self.customer_a, company=self.company_a,
            contract_id=808, contract_date=date(2026, 9, 1), price_per_square=Decimal('1000000.00'), payment_months=3
        )
        self.apt_a.status = 'SOLD'
        self.apt_a.save()
        PaymentLog.objects.create(
            contract=c, amount=Decimal('10000000.00'), payment_type='CASH',
            date_paid=timezone.make_aware(datetime.datetime(2026, 9, 5, 12, 0))
        )

        # Enable OTP verification for Company A
        prof = self.company_a.company_profile
        prof.require_termination_otp = True
        prof.save()

        self.client.force_login(self.company_a)
        init_resp = self.client.post(reverse('contract:initiate_termination', args=[c.pk]))
        self.assertEqual(init_resp.status_code, 200)
        self.assertContains(init_resp, f'#{c.contract_id}')
        mock_sms.assert_called_once()
        self.assertIn('No808', mock_sms.call_args[0][1])

        # Wrong OTP rejected
        self.client.post(reverse('contract:confirm_termination', args=[c.pk]), {
            'otp_code': '000000', 'reason': 'Bad OTP', 'fine_amount': '1000000'
        })
        c.refresh_from_db()
        self.assertEqual(c.status, Contract.STATUS_ACTIVE)

        # Valid OTP terminates contract & resets apartment
        otp_code = cache.get(f'term_otp_{c.id}')
        confirm_resp = self.client.post(reverse('contract:confirm_termination', args=[c.pk]), {
            'otp_code': otp_code, 'reason': 'Mutual agreement', 'fine_amount': '1500000'
        })
        self.assertRedirects(confirm_resp, reverse('contract:terminated_list'))
        c.refresh_from_db()
        self.apt_a.refresh_from_db()
        self.assertEqual(c.status, Contract.STATUS_TERMINATED)
        self.assertEqual(self.apt_a.status, 'AVAILABLE')

        term = TerminateContract.objects.get(contract=c)
        self.assertEqual(term.planned_refund, Decimal('8500000.00'))

        # Terminated list and dashboard both render #808 (custom contract_id, NOT db pk)
        list_resp = self.client.get(reverse('contract:terminated_list'))
        self.assertContains(list_resp, '#808')

        dash_resp = self.client.get(reverse('contract:termination_dashboard', args=[c.pk]))
        self.assertEqual(dash_resp.status_code, 200)
        self.assertContains(dash_resp, '#808')

        # Process refund + duplicate check
        self.client.post(reverse('contract:process_refund', args=[c.pk]), {'amount': '2500000', 'payment_method': 'CASH'})
        self.client.post(reverse('contract:process_refund', args=[c.pk]), {'amount': '2500000', 'payment_method': 'CASH'})
        term.refresh_from_db()
        self.assertEqual(term.paid_refund, Decimal('2500000.00'))
        self.assertEqual(TerminateContractPayment.objects.filter(termination=term).count(), 1)

        # Staff without permission cannot access termination views
        role_none = Role.objects.create(company=self.company_a, name='Limited', permissions=[])
        staff_none = CustomUser.objects.create_user(phone_number='+998907000009', password='p', is_staff_member=True)
        StaffProfile.objects.create(user=staff_none, company=self.company_a, role=role_none)
        self.client.force_login(staff_none)
        self.assertEqual(self.client.get(reverse('contract:terminated_list')).status_code, 403)

    @patch('contract.tasks.send_sms', return_value=True)
    def test_process_daily_payment_reminders_task(self, mock_sms):
        company, customer, building, apt = self._create_company_and_unit('07', area='20.00')
        today = timezone.now().date()
        c = Contract.objects.create(
            apartment=apt, customer=customer, company=company,
            contract_id=612, contract_date=today - timedelta(days=10),
            price_per_square=Decimal('1000000.00'), payment_months=1
        )
        rec = c.payment_records.first()
        rec.due_date = today - timedelta(days=5)
        rec.save()

        # Second record due in 3 days
        upcoming = PaymentRecord.objects.create(
            contract=c, month_number=2, due_date=today + timedelta(days=3),
            plan_amount=Decimal('5000000.00'), debt=Decimal('5000000.00')
        )

        result = process_daily_payment_reminders()
        self.assertIn('1 overdue alerts', result)
        self.assertIn('1 upcoming reminders', result)
        rec.refresh_from_db()
        self.assertTrue(rec.is_late)
        self.assertEqual(mock_sms.call_count, 2)
        for call in mock_sms.call_args_list:
            self.assertIn('No612', call[0][1])

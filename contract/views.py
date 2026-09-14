from decimal import Decimal
import openpyxl
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.db import transaction
from django.db.models import Q

from .models import Contract, PaymentRecord, PaymentLog, ContractTemplate
from .forms import ContractWizardForm, PaymentLogForm
from users.models import CustomUser
from building.models import Apartment
from building.views import get_user_company
from .utils.utils import number_to_words, amount_to_words_ru, MONTHS_UZ

@login_required
def contract_list(request):
    """List all active contracts for the company"""
    if not request.user.is_company:
        return redirect('dashboard:home')
        
    contracts = Contract.objects.filter(company=request.user).order_by('-created_at')
    
    query = request.GET.get('q', '').strip()
    if query:
        contracts = contracts.filter(
            Q(customer__phone_number__icontains=query) |
            Q(customer__full_name__icontains=query) |
            Q(id__icontains=query)
        )
    
    return render(request, 'contract/list.html', {
        'contracts': contracts,
        'page_title': _('Contracts'),
    })


@login_required
def contract_detail(request, pk):
    """View details of a specific contract and its financial schedule"""
    company = get_user_company(request.user)

    contract = get_object_or_404(Contract, pk=pk, company=company)
    
    if contract.status == Contract.STATUS_TERMINATED and request.GET.get('view') != 'schedule':
        return redirect('contract:termination_dashboard', pk=contract.pk)

    records = list(contract.payment_records.all().order_by('month_number'))
    payment_logs = contract.payment_logs.all().order_by('-date_paid')

    running_plan = Decimal('0.00')
    running_paid = Decimal('0.00')
    for r in records:
        running_plan += r.plan_amount
        running_paid += r.paid_amount
        net_balance = running_plan - running_paid
        r.running_balance_abs = abs(net_balance)
        r.is_running_debt = net_balance > 0
        r.is_running_credit = net_balance < 0
        r.is_running_zero = net_balance == 0

    total_paid = sum(log.amount for log in payment_logs)
    global_balance = running_plan - total_paid
    total_remaining_debt = max(Decimal('0.00'), global_balance)
    total_excess = max(Decimal('0.00'), -global_balance)

    next_due_record = next((r for r in records if r.is_running_debt), None)
    next_due_amount = next_due_record.running_balance_abs if next_due_record else Decimal('0.00')

    available_templates = ContractTemplate.objects.filter(company=contract.company)

    return render(request, 'contract/detail.html', {
        'contract': contract,
        'records': records,
        'payment_logs': payment_logs,
        'total_paid': total_paid,
        'total_remaining_debt': total_remaining_debt,
        'total_excess': total_excess,
        'next_due_record': next_due_record,
        'next_due_amount': next_due_amount,
        'available_templates': available_templates,
        'page_title': f"{_('Contract')} #{contract.id}",
        'payment_form': PaymentLogForm()
    })


@login_required
@transaction.atomic
def contract_create(request):
    """Wizard to create a new contract"""
    company = get_user_company(request.user)
    initial_apartment = None
        
    if request.method == 'POST':
        form = ContractWizardForm(request.POST, request.FILES, company=company)
        if form.is_valid():
            mode = form.cleaned_data.get('customer_mode', 'existing')
            
            if mode == 'existing':
                customer = form.cleaned_data['existing_customer']
            else:
                customer = CustomUser.objects.create(
                    phone_number=form.cleaned_data['new_customer_phone'],
                    full_name=form.cleaned_data['new_customer_name'],
                    gender=form.cleaned_data.get('new_customer_gender', ''),
                    passport_series=form.cleaned_data.get('new_customer_passport_series', ''),
                    passport_jshshr=form.cleaned_data.get('new_customer_passport_jshshr', ''),
                    passport_issued_by=form.cleaned_data.get('new_customer_passport_issued_by', ''),
                    passport_date_of_issue=form.cleaned_data.get('new_customer_passport_date_of_issue'),
                    passport_scan=form.cleaned_data.get('new_customer_passport_scan'),
                    is_customer=True
                )
                
            # 2. Create Contract
            contract = form.save(commit=False)
            contract.company = company
            contract.customer = customer
            contract.save()  # Signal generates PaymentRecords here!
            
            # 3. Mark Apartment as Sold
            apartment = contract.apartment
            apartment.status = 'SOLD'
            apartment.save(update_fields=['status'])
            
            messages.success(request, _("Contract successfully generated for {}!").format(customer.full_name or customer.phone_number))
            return redirect('contract:detail', pk=contract.pk)
        else:
            apt_id = request.POST.get('apartment')
            if apt_id:
                initial_apartment = Apartment.objects.filter(pk=apt_id, building__company=company).first()
    else:
        apartment_id = request.GET.get('apartment')
        initial_data = {}
        if apartment_id:
            apt_obj = Apartment.objects.filter(pk=apartment_id, building__company=company, status='AVAILABLE').first()
            if apt_obj:
                initial_data['apartment'] = apt_obj.pk
                initial_apartment = apt_obj
        form = ContractWizardForm(company=company, initial=initial_data)
        
    return render(request, 'contract/form.html', {
        'form': form,
        'initial_apartment': initial_apartment,
        'page_title': _('Create Contract')
    })


@login_required
def process_payment(request, pk):
    """Process a payment for a contract"""
    company = get_user_company(request.user)

    contract = get_object_or_404(Contract, pk=pk, company=company)
    
    if contract.status == Contract.STATUS_TERMINATED and request.GET.get('view') != 'schedule':
        return redirect('contract:termination_dashboard', pk=contract.pk)

    
    if request.method == 'POST':
        form = PaymentLogForm(request.POST, request.FILES)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.contract = contract
            payment.save()  # Signal cascades debt recalculation
            
            messages.success(request, _("Payment logged successfully!"))
            return redirect('contract:receipt', payment_id=payment.pk)
        else:
            messages.error(request, _("Invalid payment data. Please check the entered amount."))
            
    return redirect('contract:detail', pk=contract.pk)





import random
from django.core.cache import cache
from django.utils import timezone
from .models import TerminateContract, TerminateContractPayment
from .docx_generator import generate_contract_docx_response
from .utils.utils import number_to_words
from otp.services import send_sms

from .docx_generator import generate_contract_docx_response

@login_required
def download_docx_contract(request, pk):
    """Download the official .docx legal contract."""
    template_id = request.GET.get('template_id')
    return generate_contract_docx_response(pk, template_id=template_id)




@login_required
def download_import_template(request):
    """Generate a blank Excel template for bulk payment imports."""
    if not getattr(request.user, 'is_company', False) and not getattr(request.user, 'is_staff_member', False):
        return redirect('dashboard:home')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Payments Template"

    headers = ['Sana (DD.MM.YYYY)', 'Summa', "To'lov turi"]
    ws.append(headers)

    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = openpyxl.styles.Font(bold=True)
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 20

    # Data validation for Payment Type
    from openpyxl.worksheet.datavalidation import DataValidation
    dv = DataValidation(type="list", formula1='"Cash,Card,Bank Transfer,Material"', allow_blank=True)
    ws.add_data_validation(dv)
    # Apply to C2:C1000
    dv.add('C2:C1000')

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Payment_Template.xlsx"'
    wb.save(response)
    return response


@login_required
def import_payments_excel(request, pk):
    """Process the uploaded Excel template and bulk create payment logs."""
    company = get_user_company(request.user)

    contract = get_object_or_404(Contract, pk=pk, company=company)
    
    if contract.status == Contract.STATUS_TERMINATED and request.GET.get('view') != 'schedule':
        return redirect('contract:termination_dashboard', pk=contract.pk)


    if request.method == 'POST':
        if contract.payment_logs.count() > 0:
            messages.error(request, _("Cannot import payments: Contract already has existing payments."))
            return redirect('contract:detail', pk=contract.pk)

        excel_file = request.FILES.get('file')
        if not excel_file or not excel_file.name.endswith('.xlsx'):
            messages.error(request, _("Please upload a valid .xlsx file."))
            return redirect('contract:detail', pk=contract.pk)

        try:
            wb = openpyxl.load_workbook(excel_file)
            ws = wb.active

            type_mapping = {
                'cash': PaymentLog.PAYMENT_TYPE_CASH,
                'card': PaymentLog.PAYMENT_TYPE_CARD,
                'bank transfer': PaymentLog.PAYMENT_TYPE_BANK,
                'material': PaymentLog.PAYMENT_TYPE_MATERIAL,
            }

            import datetime

            payments_created = 0
            for row in ws.iter_rows(min_row=2, values_only=True):
                raw_date, raw_amount, raw_type = row[0], row[1], row[2]
                
                # Skip completely empty rows
                if not raw_date and not raw_amount:
                    continue

                try:
                    amount = Decimal(str(raw_amount))
                except:
                    continue  # Skip invalid amount
                
                # Parse Date
                date_paid = timezone.now()
                if isinstance(raw_date, datetime.datetime):
                    date_paid = timezone.make_aware(raw_date) if timezone.is_naive(raw_date) else raw_date
                elif isinstance(raw_date, str):
                    try:
                        parsed = datetime.datetime.strptime(raw_date, '%d.%m.%Y')
                        date_paid = timezone.make_aware(parsed)
                    except:
                        pass

                # Parse Payment Type
                payment_type = PaymentLog.PAYMENT_TYPE_CASH
                if raw_type and str(raw_type).strip().lower() in type_mapping:
                    payment_type = type_mapping[str(raw_type).strip().lower()]

                payment = PaymentLog(
                    contract=contract,
                    amount=amount,
                    payment_type=payment_type,
                    date_paid=date_paid
                )
                payment.save()
                payments_created += 1

            messages.success(request, _(f"Successfully imported {payments_created} payments!"))
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error importing payments: {e}")
            messages.error(request, _("Failed to process Excel file. Please ensure it matches the template."))

    return redirect('contract:detail', pk=contract.pk)

@login_required
def download_payments_excel(request, pk):
    """Download the payment history as an Excel file."""
    company = get_user_company(request.user)

    contract = get_object_or_404(Contract, pk=pk, company=company)
    
    if contract.status == Contract.STATUS_TERMINATED and request.GET.get('view') != 'schedule':
        return redirect('contract:termination_dashboard', pk=contract.pk)

    
    # Create an Excel workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Payments"
    
    # Headers
    headers = ['ID', 'Sana', 'Summa', 'To\'lov turi', 'Tranzaksiya ID', 'Xodim']
    ws.append(headers)
    
    # Style the header row
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = openpyxl.styles.Font(bold=True)
    
    # Fetch logs
    payment_logs = contract.payment_logs.all().order_by('-date_paid')
    
    for log in payment_logs:
        staff_name = "Noma'lum"
        try:
            # We assume added_by or similar exists, otherwise leave blank
            pass
        except:
            pass
            
        ws.append([
            log.id,
            log.date_paid.strftime("%d.%m.%Y"),
            float(log.amount),
            log.get_payment_type_display(),
            log.transaction_id or '',
            ''
        ])
        
    # Return response
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="Payments_{contract.id}.xlsx"'
    wb.save(response)
    return response


@login_required
def receipt_view(request, payment_id):
    """Printable payment receipt view in KO-1 standard"""
    from .utils.utils import amount_to_words_ru, MONTHS_RU
    payment = get_object_or_404(PaymentLog, pk=payment_id)
    contract = payment.contract
    
    # Use robust fallback for company name
    try:
        company_name = contract.company.company_profile.company_name
    except AttributeError:
        company_name = contract.company.get_full_name() or contract.company.username
        
    customer_name = contract.customer.full_name or contract.customer.phone_number
    customer_desc = f"{customer_name} №{contract.id} сонли шартномага асосан тўлов"
    
    amount_words = amount_to_words_ru(payment.amount)
    if payment.payment_type == PaymentLog.PAYMENT_TYPE_CARD:
        payment_method_upper = 'ПЛАСТИК'
    else:
        payment_method_upper = ''
    
    # Format date: 4 сентября 2026 г.
    day = payment.date_paid.day
    month_name = MONTHS_RU.get(payment.date_paid.month, str(payment.date_paid.month))
    year = payment.date_paid.year
    date_ru = f"{day} {month_name} {year} г."
    
    return render(request, 'contract/receipt.html', {
        'payment': payment,
        'contract': contract,
        'company_name': company_name,
        'customer_desc': customer_desc,
        'payment_method_upper': payment_method_upper,
        'amount_words': amount_words,
        'date_ru': date_ru,
    })


@login_required
def initiate_termination(request, pk):
    """Initiates termination request, generates OTP and sends SMS to company manager"""
    company = get_user_company(request.user)
    contract = get_object_or_404(Contract, pk=pk, company=company, status=Contract.STATUS_ACTIVE)
    
    if request.method == 'POST':
        # Generate 6-digit random OTP
        otp_code = f"{random.randint(100000, 999999)}"
        cache_key = f"term_otp_{contract.id}"
        cache.set(cache_key, otp_code, timeout=300)  # 5 minutes TTL
        
        # Send SMS to company user
        company_phone = str(contract.company.phone_number)
        msg = f"TrustBuilding: №{contract.id} shartnomani bekor qilish uchun tasdiqlash kodi: {otp_code}"
        try:
            send_sms(company_phone, msg)
            messages.info(request, _("A 6-digit OTP code has been sent to your phone for verification."))
        except Exception as e:
            messages.warning(request, _("OTP generated ({}) but SMS failed: {}").format(otp_code, e))
            
        total_paid = sum(p.amount for p in contract.payment_logs.all())
        return render(request, 'contract/confirm_termination.html', {
            'contract': contract,
            'total_paid': total_paid,
            'page_title': _("Confirm Contract Termination")
        })
        
    return redirect('contract:detail', pk=pk)


@login_required
def confirm_termination(request, pk):
    """Verifies OTP and executes contract termination & apartment archiving"""
    company = get_user_company(request.user)
    contract = get_object_or_404(Contract, pk=pk, company=company, status=Contract.STATUS_ACTIVE)
    
    if request.method == 'POST':
        otp_input = request.POST.get('otp_code', '').strip()
        reason = request.POST.get('reason', '').strip()
        fine_amount = request.POST.get('fine_amount', '0').strip()
        
        cache_key = f"term_otp_{contract.id}"
        cached_otp = cache.get(cache_key)
        
        if cached_otp and cached_otp == otp_input:
            fine_dec = Decimal(fine_amount or 0)
            
            # Execute apartment cloning & status update
            contract.terminate(reason=reason, fine_amount=fine_dec)
            
            # Create TerminateContract record
            total_paid = sum(p.amount for p in contract.payment_logs.all())
            planned_refund = max(Decimal(0), total_paid - fine_dec)
            
            TerminateContract.objects.create(
                contract=contract,
                termination_date=timezone.now().date(),
                termination_reason=reason,
                fine_amount=fine_dec,
                planned_refund=planned_refund
            )
            
            cache.delete(cache_key)
            messages.success(request, _("Contract #{} terminated successfully! Apartment reset to AVAILABLE.").format(contract.id))
            return redirect('contract:terminated_list')
        else:
            messages.error(request, _("Invalid or expired OTP code."))
            total_paid = sum(p.amount for p in contract.payment_logs.all())
        return render(request, 'contract/confirm_termination.html', {
            'contract': contract,
            'total_paid': total_paid,
            'page_title': _("Confirm Contract Termination")
        })
            
    return redirect('contract:detail', pk=pk)


@login_required

@login_required
def termination_dashboard(request, pk):
    """Dashboard for managing refunds on a terminated contract."""
    company = get_user_company(request.user)
    contract = get_object_or_404(Contract, pk=pk, company=company, status=Contract.STATUS_TERMINATED)
    termination = get_object_or_404(TerminateContract, contract=contract)
    
    refund_payments = termination.refund_payments.all().order_by('-payment_date', '-created_at')
    remaining_refund = max(Decimal(0), termination.planned_refund - termination.paid_refund)
    
    return render(request, 'contract/termination_dashboard.html', {
        'contract': contract,
        'termination': termination,
        'refund_payments': refund_payments,
        'remaining_refund': remaining_refund,
        'page_title': _("Terminated Contract Dashboard")
    })

@login_required
def process_refund(request, pk):
    """Process a refund payment to the customer."""
    company = get_user_company(request.user)
    contract = get_object_or_404(Contract, pk=pk, company=company, status=Contract.STATUS_TERMINATED)
    termination = get_object_or_404(TerminateContract, contract=contract)
    
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', '0').strip() or 0)
        payment_method = request.POST.get('payment_method', PaymentLog.PAYMENT_TYPE_CASH)
        notes = request.POST.get('notes', '')
        
        if amount > 0:
            TerminateContractPayment.objects.create(
                termination=termination,
                amount=amount,
                payment_type=payment_method,
                notes=notes,
                payment_date=timezone.now().date()
            )
            messages.success(request, _("Refund payment recorded successfully!"))
        else:
            messages.error(request, _("Amount must be greater than 0."))
            
    return redirect('contract:termination_dashboard', pk=contract.pk)

@login_required
def terminated_contracts_list(request):
    """List all terminated contracts"""
    company = get_user_company(request.user)
    terminations = TerminateContract.objects.filter(contract__company=company).select_related(
        'contract', 'contract__customer', 'contract__apartment'
    ).order_by('-created_at')
    
    return render(request, 'contract/terminated_list.html', {
        'terminations': terminations,
        'page_title': _("Terminated Contracts")
    })


@login_required
def staff_quick_payment(request):
    """Quick payment terminal view for sales staff"""
    company = get_user_company(request.user)
    query = request.GET.get('q', '').strip()
    selected_customer_id = request.GET.get('customer', '')
    
    customers = CustomUser.objects.filter(is_customer=True)
    if query:
        customers = customers.filter(
            Q(phone_number__icontains=query) | Q(full_name__icontains=query)
        )
        
    selected_customer = None
    contracts = []
    if selected_customer_id:
        selected_customer = get_object_or_404(CustomUser, pk=selected_customer_id, is_customer=True)
        contracts = Contract.objects.filter(customer=selected_customer, company=company, status=Contract.STATUS_ACTIVE)
        
    return render(request, 'contract/quick_payment.html', {
        'customers': customers[:15],
        'selected_customer': selected_customer,
        'contracts': contracts,
        'query': query,
        'payment_form': PaymentLogForm(),
        'page_title': _("Staff Payment Terminal")
    })


@login_required
def search_customers_api(request):
    """Real-time HTMX customer search endpoint for thousands of records"""
    query = request.GET.get('q', '').strip()
    customers = CustomUser.objects.filter(is_customer=True)
    if query:
        customers = customers.filter(
            Q(full_name__icontains=query) |
            Q(phone_number__icontains=query) |
            Q(passport_jshshr__icontains=query) |
            Q(passport_series__icontains=query)
        )
    customers = customers.order_by('-created_at')[:20]
    return render(request, 'contract/partials/customer_search_results.html', {'customers': customers})


@login_required
def search_apartments_api(request):
    """Real-time HTMX apartment search endpoint when unit is not pre-selected"""
    company = get_user_company(request.user)
    query = request.GET.get('q', '').strip()
    apartments = Apartment.objects.filter(
        building__company=company,
        status='AVAILABLE',
        is_real=True
    )
    if query:
        apartments = apartments.filter(
            Q(apartment_number__icontains=query) |
            Q(building__name__icontains=query) |
            Q(living_room_count__icontains=query)
        )
    apartments = apartments.order_by('building__name', 'entrance_number', 'floor_number', 'apartment_number')[:30]
    return render(request, 'contract/partials/apartment_search_results.html', {'apartments': apartments})


# ==========================================
# CONTRACT TEMPLATES MANAGEMENT
# ==========================================

@login_required
def template_list(request):
    """List all contract templates for the company."""
    if not getattr(request.user, 'is_company', False):
        messages.error(request, _("Access denied."))
        return redirect('dashboard:home')
        
    templates = ContractTemplate.objects.filter(company=request.user)
    return render(request, 'contract/template_list.html', {'templates': templates})

@login_required
def template_create(request):
    """Upload a new contract template."""
    if not getattr(request.user, 'is_company', False):
        messages.error(request, _("Access denied."))
        return redirect('dashboard:home')
        
    if request.method == 'POST':
        name = request.POST.get('name')
        file = request.FILES.get('file')
        is_default = request.POST.get('is_default') == 'on'
        
        if name and file:
            # Magic: Modify the uploaded document to make the schedule table dynamic
            try:
                from docx import Document
                import io
                
                # Read into python-docx
                doc = Document(file)
                for table in doc.tables:
                    try:
                        header = table.rows[0].cells[1].text.strip().lower()
                        if 'тўлов номи' in header or 'тўлов суммаси' in header:
                            jami_idx = -1
                            for i, row in enumerate(table.rows):
                                if len(row.cells) > 1 and 'Жами' in row.cells[1].text:
                                    jami_idx = i
                                    break
                            
                            if jami_idx > 4:
                                # Row 1 is {%tr for %}
                                table.rows[1].cells[0].text = "{%tr for r in schedule %}"
                                for c in table.rows[1].cells[1:]: c.text = ""
                                
                                # Row 2 is data
                                table.rows[2].cells[0].text = "{{ loop.index }}"
                                table.rows[2].cells[1].text = "{{ r.name }}"
                                table.rows[2].cells[2].text = "{{ r.amount }}"
                                if len(table.rows[2].cells) > 3:
                                    table.rows[2].cells[3].text = "{{ r.date }}"
                                
                                # Row 3 is {%tr endfor %}
                                table.rows[3].cells[0].text = "{%tr endfor %}"
                                for c in table.rows[3].cells[1:]: c.text = ""
                                
                                # Delete all rows from 4 up to jami_idx - 1
                                for _idx in range(4, jami_idx):
                                    tr = table.rows[4]._tr
                                    tr.getparent().remove(tr)
                                    
                                # Replace Jami row amounts
                                if len(table.rows[4].cells) > 2:
                                    table.rows[4].cells[2].text = "«Шартнома_суммаси»"
                                break
                    except Exception:
                        continue
                
                # Save back to a BytesIO object
                file_io = io.BytesIO()
                doc.save(file_io)
                file_io.seek(0)
                
                from django.core.files.uploadedfile import InMemoryUploadedFile
                file = InMemoryUploadedFile(
                    file_io, 'file', file.name,
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    file_io.getbuffer().nbytes, None
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Error parsing table: {e}")
                
            ContractTemplate.objects.create(
                company=request.user,
                name=name,
                file=file,
                is_default=is_default
            )
            messages.success(request, _("Template uploaded successfully."))
            return redirect('contract:template_list')
            
        messages.error(request, _("Please provide a name and a valid .docx file."))
        
    return redirect('contract:template_list')

@login_required
def template_delete(request, pk):
    if not getattr(request.user, 'is_company', False):
        return redirect('dashboard:home')
        
    template = get_object_or_404(ContractTemplate, pk=pk, company=request.user)
    if request.method == 'POST':
        template.delete()
        messages.success(request, _("Template deleted."))
    return redirect('contract:template_list')

@login_required
def template_set_default(request, pk):
    if not getattr(request.user, 'is_company', False):
        return redirect('dashboard:home')
        
    template = get_object_or_404(ContractTemplate, pk=pk, company=request.user)
    if request.method == 'POST':
        template.is_default = True
        template.save()
        messages.success(request, _("Default template updated."))
    return redirect('contract:template_list')

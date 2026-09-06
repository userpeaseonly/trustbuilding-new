from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.db import transaction
from django.db.models import Q

from .models import Contract, PaymentRecord, PaymentLog
from .forms import ContractWizardForm, PaymentLogForm
from users.models import CustomUser
from building.models import Apartment
from building.views import get_user_company

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

    return render(request, 'contract/detail.html', {
        'contract': contract,
        'records': records,
        'payment_logs': payment_logs,
        'total_paid': total_paid,
        'total_remaining_debt': total_remaining_debt,
        'total_excess': total_excess,
        'next_due_record': next_due_record,
        'next_due_amount': next_due_amount,
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

@login_required
def download_docx_contract(request, pk):
    """Download pre-filled official .docx legal contract"""
    return generate_contract_docx_response(pk)


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
            
        return render(request, 'contract/confirm_termination.html', {
            'contract': contract,
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
            return render(request, 'contract/confirm_termination.html', {
                'contract': contract,
                'page_title': _("Confirm Contract Termination")
            })
            
    return redirect('contract:detail', pk=pk)


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


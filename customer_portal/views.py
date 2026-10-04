from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from contract.models import Contract

@login_required
def home(request):
    """Customer Dashboard showing all their contracts"""
    # Double check authorization
    if getattr(request.user, 'is_company', False) or getattr(request.user, 'is_staff_member', False):
        return redirect('dashboard:home')
    
    if not request.user.is_customer:
        return redirect('users:login')

    # Get the customer's contracts
    contracts = Contract.objects.filter(customer=request.user).select_related('apartment__building')
    
    context = {
        'contracts': contracts,
    }
    return render(request, 'customer_portal/home.html', context)

@login_required
def contract_detail(request, contract_id):
    """View details and payment schedule for a specific contract"""
    if getattr(request.user, 'is_company', False) or getattr(request.user, 'is_staff_member', False):
        return redirect('dashboard:home')
        
    if not request.user.is_customer:
        return redirect('users:login')

    # Security: Ensure they can only view THEIR OWN contract
    contract = get_object_or_404(Contract, pk=contract_id, customer=request.user)
    
    from decimal import Decimal
    from contract.models import ContractTemplate

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
    from contract.models import PaymentLog
    total_cash_paid = sum(log.amount for log in payment_logs if log.payment_type == PaymentLog.PAYMENT_TYPE_CASH)
    total_bank_paid = sum(log.amount for log in payment_logs if log.payment_type == PaymentLog.PAYMENT_TYPE_BANK)

    global_balance = running_plan - total_paid
    total_remaining_debt = max(Decimal('0.00'), global_balance)
    total_excess = max(Decimal('0.00'), -global_balance)

    next_due_record = next((r for r in records if r.is_running_debt), None)
    next_due_amount = next_due_record.running_balance_abs if next_due_record else Decimal('0.00')

    available_templates = ContractTemplate.objects.filter(company=contract.company)
    
    context = {
        'contract': contract,
        'records': records,
        'payment_logs': payment_logs,
        'total_paid': total_paid,
        'total_cash_paid': total_cash_paid,
        'total_bank_paid': total_bank_paid,
        'total_remaining_debt': total_remaining_debt,
        'total_excess': total_excess,
        'next_due_record': next_due_record,
        'next_due_amount': next_due_amount,
        'available_templates': available_templates,
    }
    return render(request, 'customer_portal/contract_detail.html', context)



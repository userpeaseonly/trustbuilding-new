import re

with open('contract/views.py', 'r') as f:
    content = f.read()

new_views = """
@login_required
def termination_dashboard(request, pk):
    \"\"\"Dashboard for managing refunds on a terminated contract.\"\"\"
    company = get_user_company(request.user)
    contract = get_object_or_404(Contract, pk=pk, company=company, status=Contract.STATUS_TERMINATED)
    termination = get_object_or_404(TerminateContract, contract=contract)
    
    refund_payments = termination.refund_payments.all().order_by('-payment_date', '-created_at')
    
    return render(request, 'contract/termination_dashboard.html', {
        'contract': contract,
        'termination': termination,
        'refund_payments': refund_payments,
        'page_title': _("Terminated Contract Dashboard")
    })

@login_required
def process_refund(request, pk):
    \"\"\"Process a refund payment to the customer.\"\"\"
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
                payment_method=payment_method,
                notes=notes,
                payment_date=timezone.now().date()
            )
            messages.success(request, _("Refund payment recorded successfully!"))
        else:
            messages.error(request, _("Amount must be greater than 0."))
            
    return redirect('contract:termination_dashboard', pk=contract.pk)
"""

parts = content.split('def terminated_contracts_list')
if len(parts) == 2:
    new_content = parts[0] + new_views + '\n@login_required\ndef terminated_contracts_list' + parts[1]
    with open('contract/views.py', 'w') as f:
        f.write(new_content)
    print("Success")
else:
    print("Could not find anchor")

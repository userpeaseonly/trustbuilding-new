import re

with open('contract/views.py', 'r') as f:
    content = f.read()

new_view = """
@login_required
def termination_dashboard(request, pk):
    \"\"\"Dashboard for managing refunds on a terminated contract.\"\"\"
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
"""

content = re.sub(r'@login_required\ndef termination_dashboard.*?return render.*?\}\)', new_view.strip(), content, flags=re.DOTALL)

with open('contract/views.py', 'w') as f:
    f.write(content)
print("Success")

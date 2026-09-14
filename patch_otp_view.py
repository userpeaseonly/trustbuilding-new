import re

with open('contract/views.py', 'r') as f:
    content = f.read()

new_ctx = """
        total_paid = sum(p.amount for p in contract.payment_logs.all())
        return render(request, 'contract/confirm_termination.html', {
            'contract': contract,
            'total_paid': total_paid,
            'page_title': _("Confirm Contract Termination")
        })
"""

content = re.sub(r'return render\(request, \'contract/confirm_termination\.html\', \{(.*?)\}\)', new_ctx.strip(), content, flags=re.DOTALL)

with open('contract/views.py', 'w') as f:
    f.write(content)
print("Success")

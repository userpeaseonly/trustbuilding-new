import re

with open('contract/views.py', 'r') as f:
    content = f.read()

redirect_logic = """
    contract = get_object_or_404(Contract, pk=pk, company=company)
    
    if contract.status == Contract.STATUS_TERMINATED:
        return redirect('contract:termination_dashboard', pk=contract.pk)
"""

content = content.replace("    contract = get_object_or_404(Contract, pk=pk, company=company)", redirect_logic)

with open('contract/views.py', 'w') as f:
    f.write(content)
print("Success")

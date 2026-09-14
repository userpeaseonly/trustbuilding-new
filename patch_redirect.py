with open('contract/views.py', 'r') as f:
    content = f.read()

old_redirect = """    if contract.status == Contract.STATUS_TERMINATED:
        return redirect('contract:termination_dashboard', pk=contract.pk)"""

new_redirect = """    if contract.status == Contract.STATUS_TERMINATED and request.GET.get('view') != 'schedule':
        return redirect('contract:termination_dashboard', pk=contract.pk)"""

content = content.replace(old_redirect, new_redirect)

with open('contract/views.py', 'w') as f:
    f.write(content)
print("Success")

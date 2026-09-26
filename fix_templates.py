import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings.local')
django.setup()

from contract.models import ContractTemplate

for tp in ContractTemplate.objects.all():
    if not tp.company.is_company:
        print(f"Found orphaned template {tp.name} assigned to {tp.company.phone_number}")
        # Try to find their actual company
        if hasattr(tp.company, 'staff_profile'):
            actual_company = tp.company.staff_profile.company
            tp.company = actual_company
            tp.save()
            print(f"Reassigned template to company {actual_company.phone_number}")

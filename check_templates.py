import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings.local')
django.setup()

from contract.models import ContractTemplate

for tp in ContractTemplate.objects.all():
    print(f"ID={tp.id}, Name={tp.name}, CompanyID={tp.company_id}, is_company={tp.company.is_company}, Phone={tp.company.phone_number}")
    if getattr(tp.company, 'is_staff_member', False):
        if hasattr(tp.company, 'staff_profile'):
            print(f"  -> Uploaded by staff! Actual company ID: {tp.company.staff_profile.company.id}")
            tp.company = tp.company.staff_profile.company
            tp.save()
            print("  -> FIXED!")

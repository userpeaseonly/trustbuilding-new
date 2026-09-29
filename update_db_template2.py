import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()

from contract.models import ContractTemplate
from django.core.files import File

with open('/tmp/bunyodkorshartnomashablon_cambria.docx', 'rb') as f:
    django_file = File(f, name='bunyodkorshartnomashablon.docx')
    templates = ContractTemplate.objects.all()
    count = 0
    for t in templates:
        t.file.save('bunyodkorshartnomashablon.docx', django_file)
        t.save()
        count += 1
    print(f"Updated {count} templates in DB.")

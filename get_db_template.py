import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()

from contract.models import ContractTemplate

t = ContractTemplate.objects.first()
with open('/tmp/latest_from_db.docx', 'wb') as f:
    f.write(t.file.read())
print("Saved to /tmp/latest_from_db.docx")

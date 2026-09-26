import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings.local')
django.setup()

from contract.models import Contract
for c in Contract.objects.all()[:1]:
    if c.total_amount > 0:
        percent = (c.down_payment_amount / c.total_amount) * 100
        print(f"Down payment: {c.down_payment_amount}, Total: {c.total_amount}, %: {percent:.0f}")

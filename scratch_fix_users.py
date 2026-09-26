import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings.local')
django.setup()

from users.models import CustomUser

bad_users = CustomUser.objects.exclude(phone_number__startswith='+')
count = bad_users.count()
print(f"Found {count} users without a '+' prefix.")

for u in bad_users:
    print(f"Deleting bad user: {u.phone_number} (ID: {u.id})")
    u.delete()


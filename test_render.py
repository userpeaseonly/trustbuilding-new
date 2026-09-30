import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()

from django.test import Client
from users.models import CustomUser

c = Client()
user = CustomUser.objects.filter(is_company=True).first()
c.force_login(user)

response = c.get('/contract/')
html = response.content.decode('utf-8')

import re
match = re.search(r'<form method="get"[^>]*>.*?</form>', html, re.DOTALL)
if match:
    print(match.group(0))
else:
    print("Form not found!")

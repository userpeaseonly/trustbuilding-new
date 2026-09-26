import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings.local')
django.setup()

from otp.services import EskizSMS

# Test latin string
latin_msg = "Hello World"
print(EskizSMS.calculate_sms_cost('998901234567', latin_msg)) # Beeline

# Test ucs2 string
ucs2_msg = "Салом, Алишер" # Cyrillic
print(EskizSMS.calculate_sms_cost('998971234567', ucs2_msg)) # Mobiuz


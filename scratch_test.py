import sys
sys.path.append('.')
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "application.settings.local")
import django
django.setup()

from dashboard.views import reconciliation_report
print("Function imported successfully")

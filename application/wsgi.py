import os

from dotenv import load_dotenv

load_dotenv()

from django.core.wsgi import get_wsgi_application

print("Django Env from wsgi", os.environ.get('DJANGO_ENV'))

if os.environ.get('DJANGO_ENV') == 'production':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings.production')
    print('prod')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings.local')
    print('local')
application = get_wsgi_application()

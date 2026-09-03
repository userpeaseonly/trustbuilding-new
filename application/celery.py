import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')

app = Celery('trustbuilding')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

# Configure periodic tasks
from celery.schedules import crontab

app.conf.beat_schedule = {
    'daily-payment-reminders': {
        'task': 'contract.tasks.process_daily_payment_reminders',
        'schedule': crontab(hour=10, minute=0),  # Run every day at 10 AM
    },
}

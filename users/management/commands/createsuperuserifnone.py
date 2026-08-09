from django.contrib.auth import get_user_model
from django.core.management import BaseCommand
import os

class Command(BaseCommand):
    help = 'Create a superuser if none exists'

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(is_superuser=True).exists():
            self.stdout.write(self.style.SUCCESS('No superuser found. Creating one...'))
            User.objects.create_superuser(
                phone_number=os.environ.get('ADMIN_PHONE', '+998901234567'),
                password=os.environ.get('ADMIN_PASSWORD', 'yourpassword')
            )
        else:
            self.stdout.write(self.style.WARNING('A superuser already exists.'))

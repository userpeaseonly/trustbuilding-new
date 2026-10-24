from django.core.management.base import BaseCommand
from bot.tasks import send_morning_executive_reports, send_evening_executive_reports


class Command(BaseCommand):
    help = "Manually trigger executive reports dispatch (morning or evening)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['morning', 'evening'],
            default='evening',
            help="Type of report to dispatch (morning or evening)"
        )

    def handle(self, *args, **options):
        rep_type = options['type']
        if rep_type == 'morning':
            self.stdout.write("Dispatching Morning Executive Reports (09:00 AM)...")
            res = send_morning_executive_reports()
        else:
            self.stdout.write("Dispatching Evening Executive Reports (20:00 PM)...")
            res = send_evening_executive_reports()

        self.stdout.write(self.style.SUCCESS(f"Result: {res}"))

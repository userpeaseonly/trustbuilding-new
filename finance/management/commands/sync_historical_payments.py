from django.core.management.base import BaseCommand
from contract.models import PaymentLog
from finance.signals import sync_payment_log_to_finance


class Command(BaseCommand):
    help = 'Sync existing contract PaymentLog entries into Finance transactions.'

    def handle(self, *args, **options):
        logs = PaymentLog.objects.filter(contract__isnull=False).select_related('contract', 'contract__company', 'contract__customer')
        count = 0
        for log in logs:
            sync_payment_log_to_finance(PaymentLog, log, created=False)
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Successfully synchronized {count} historical payments into Finance!'))

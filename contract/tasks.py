import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Contract, PaymentRecord
from otp.services import send_sms
from otp.transliteration import build_overdue_sms, build_upcoming_reminder_sms

logger = logging.getLogger(__name__)

@shared_task
def process_daily_payment_reminders():
    """
    Daily Celery cron task to send payment reminders via Eskiz SMS:
    1. Overdue Alerts: PaymentRecords where due_date < today and debt > 0.
    2. 3-Day Reminders: PaymentRecords where due_date == today + 3 days and debt > 0.
    """
    today = timezone.now().date()
    three_days_later = today + timedelta(days=3)

    # 1. Overdue Alerts
    overdue_records = PaymentRecord.objects.filter(
        contract__status=Contract.STATUS_ACTIVE,
        debt__gt=0,
        due_date__lt=today
    ).select_related('contract', 'contract__customer', 'contract__apartment__building')

    overdue_count = 0
    for record in overdue_records:
        record.is_late = True
        record.save(update_fields=['is_late', 'updated_at'])
        
        customer_phone = str(record.contract.customer.phone_number)
        message = build_overdue_sms(
            customer_full_name=record.contract.customer.full_name,
            contract_id=record.contract.id,
            due_date=record.due_date,
            debt_amount=record.debt
        )
        try:
            send_sms(customer_phone, message, company=record.contract.company)
            overdue_count += 1
        except Exception as e:
            logger.error(f"Failed to send overdue SMS to {customer_phone}: {e}")

    # 2. 3-Day Reminders
    upcoming_records = PaymentRecord.objects.filter(
        contract__status=Contract.STATUS_ACTIVE,
        debt__gt=0,
        due_date=three_days_later
    ).select_related('contract', 'contract__customer')

    reminder_count = 0
    for record in upcoming_records:
        customer_phone = str(record.contract.customer.phone_number)
        message = build_upcoming_reminder_sms(
            contract_id=record.contract.id,
            due_date=record.due_date,
            amount=record.debt
        )
        try:
            send_sms(customer_phone, message, company=record.contract.company)
            reminder_count += 1
        except Exception as e:
            logger.error(f"Failed to send 3-day reminder SMS to {customer_phone}: {e}")

    return f"Processed payment reminders: {overdue_count} overdue alerts, {reminder_count} upcoming reminders sent."

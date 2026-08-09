from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from dateutil.relativedelta import relativedelta
from decimal import Decimal

from users.models import CustomUser
from building.models import Apartment

class Contract(models.Model):
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_TERMINATED = 'TERMINATED'
    STATUS_COMPLETED = 'COMPLETED'
    
    STATUS_CHOICES = [
        (STATUS_ACTIVE, _('Active')),
        (STATUS_TERMINATED, _('Terminated')),
        (STATUS_COMPLETED, _('Completed')),
    ]

    apartment = models.ForeignKey(Apartment, on_delete=models.CASCADE, related_name='contracts')
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='customer_contracts', limit_choices_to={'is_customer': True})
    company = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='company_contracts', limit_choices_to={'is_company': True})
    
    contract_date = models.DateField(_("Contract Date"))
    price_per_square = models.DecimalField(_("Price per m2"), max_digits=12, decimal_places=2)
    down_payment_amount = models.DecimalField(_("Down Payment"), max_digits=15, decimal_places=2, default=0)
    discount_amount = models.DecimalField(_("Discount Amount"), max_digits=15, decimal_places=2, default=0)
    payment_months = models.PositiveIntegerField(_("Payment Duration (Months)"))
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    
    # Calculated field for caching
    total_amount = models.DecimalField(_("Total Contract Amount"), max_digits=15, decimal_places=2, editable=False, default=0)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Contract")
        verbose_name_plural = _("Contracts")

    def __str__(self):
        return f"Contract #{self.pk} - {self.customer.full_name}"

    def save(self, *args, **kwargs):
        # Calculate total amount
        if self.apartment and self.price_per_square:
            self.total_amount = self.price_per_square * self.apartment.total_area
        super().save(*args, **kwargs)


class PaymentRecord(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='payment_records')
    month_number = models.PositiveIntegerField(_("Month Number"))
    due_date = models.DateField(_("Due Date"))
    plan_amount = models.DecimalField(_("Planned Amount"), max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(_("Paid Amount"), max_digits=12, decimal_places=2, default=0)
    debt = models.DecimalField(_("Debt"), max_digits=12, decimal_places=2, default=0)
    is_late = models.BooleanField(_("Is Late"), default=False)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Payment Record")
        verbose_name_plural = _("Payment Records")
        ordering = ['contract', 'month_number']

    def __str__(self):
        return f"{self.contract} - Month {self.month_number}"


class PaymentLog(models.Model):
    PAYMENT_TYPE_CASH = 'CASH'
    PAYMENT_TYPE_CARD = 'CARD'
    PAYMENT_TYPE_BANK = 'BANK'
    PAYMENT_TYPE_MATERIAL = 'MATERIAL'

    PAYMENT_TYPE_CHOICES = [
        (PAYMENT_TYPE_CASH, _('Cash')),
        (PAYMENT_TYPE_CARD, _('Card')),
        (PAYMENT_TYPE_BANK, _('Bank Transfer')),
        (PAYMENT_TYPE_MATERIAL, _('Material')),
    ]

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='payment_logs')
    amount = models.DecimalField(_("Payment Amount"), max_digits=12, decimal_places=2)
    payment_type = models.CharField(_("Payment Type"), max_length=20, choices=PAYMENT_TYPE_CHOICES)
    transaction_id = models.CharField(_("Transaction ID"), max_length=255, blank=True, help_text=_("For bank transfers/terminal"))
    receipt_image = models.ImageField(_("Receipt Image"), upload_to='payment_receipts/', blank=True, null=True)
    date_paid = models.DateTimeField(_("Date Paid"), auto_now_add=True)
    
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("Payment Log")
        verbose_name_plural = _("Payment Logs")
        ordering = ['-date_paid']

    def __str__(self):
        return f"{self.contract} - {self.amount} ({self.payment_type})"


# --- SIGNALS ---

@receiver(post_save, sender=Contract)
def generate_payment_records(sender, instance, created, **kwargs):
    if created and instance.payment_months > 0:
        # Subtract down payment and discount from the total amount to find the installment pool
        installment_pool = instance.total_amount - instance.down_payment_amount - instance.discount_amount
        if installment_pool < 0:
            installment_pool = Decimal(0)
            
        monthly_amount = installment_pool / Decimal(instance.payment_months)
        
        records = []
        for i in range(1, instance.payment_months + 1):
            due_date = instance.contract_date + relativedelta(months=i)
            records.append(PaymentRecord(
                contract=instance,
                month_number=i,
                due_date=due_date,
                plan_amount=monthly_amount,
                debt=monthly_amount  # Initially debt is the plan amount
            ))
        PaymentRecord.objects.bulk_create(records)


def recalculate_contract_debt(contract):
    """
    Recalculate debt for all payment records of a contract.
    This cascades payments across the schedule.
    """
    total_paid = sum(log.amount for log in contract.payment_logs.all())
    
    records = list(contract.payment_records.all().order_by('month_number'))
    
    remaining_payment = total_paid
    for record in records:
        record.paid_amount = min(remaining_payment, record.plan_amount)
        record.debt = record.plan_amount - record.paid_amount
        remaining_payment = max(Decimal(0), remaining_payment - record.plan_amount)
        record.save(update_fields=['paid_amount', 'debt', 'updated_at'])


@receiver(post_save, sender=PaymentLog)
def on_payment_log_created(sender, instance, created, **kwargs):
    recalculate_contract_debt(instance.contract)


@receiver(post_delete, sender=PaymentLog)
def on_payment_log_deleted(sender, instance, **kwargs):
    recalculate_contract_debt(instance.contract)

import uuid
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
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
    down_payment_date = models.DateField(_("Down Payment Date"), null=True, blank=True)
    price_per_square = models.DecimalField(_("Price per m2"), max_digits=12, decimal_places=2)
    down_payment_amount = models.DecimalField(_("Down Payment"), max_digits=15, decimal_places=2, default=0)
    last_payment_amount = models.DecimalField(_("Last Payment"), max_digits=15, decimal_places=2, default=0)
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

    def terminate(self, reason="", fine_amount=0):
        """
        Terminate contract and reset real apartment status to AVAILABLE.
        """
        if self.status == self.STATUS_ACTIVE:
            self.status = self.STATUS_TERMINATED
            self.save(update_fields=['status', 'updated_at'])

            # Reset real apartment to AVAILABLE
            if self.apartment:
                self.apartment.status = 'AVAILABLE'
                self.apartment.save(update_fields=['status', 'updated_at'])


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
    payment_record = models.ForeignKey('PaymentRecord', on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_logs')
    amount = models.DecimalField(_("Payment Amount"), max_digits=15, decimal_places=2)
    payment_type = models.CharField(_("Payment Type"), max_length=20, choices=PAYMENT_TYPE_CHOICES)
    transaction_id = models.CharField(_("Transaction ID"), max_length=255, blank=True, help_text=_("For bank transfers/terminal"))
    receipt_image = models.ImageField(_("Receipt Image"), upload_to='payment_receipts/', blank=True, null=True)
    date_paid = models.DateTimeField(_("Date Paid"), default=timezone.now, blank=True)
    
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("Payment Log")
        verbose_name_plural = _("Payment Logs")
        ordering = ['date_paid']

    def save(self, *args, **kwargs):
        if not self.pk or not self.transaction_id:
            today_str = timezone.now().strftime("%Y%m%d")
            rand_hex = uuid.uuid4().hex[:6].upper()
            self.transaction_id = f"TX-{today_str}-{rand_hex}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.contract} - {self.amount} ({self.payment_type})"


class TerminateContract(models.Model):
    contract = models.OneToOneField(Contract, on_delete=models.CASCADE, related_name='termination')
    termination_date = models.DateField(_("Termination Date"))
    termination_reason = models.TextField(_("Termination Reason"), blank=True)
    fine_amount = models.DecimalField(_("Fine Amount"), max_digits=15, decimal_places=2, default=0)
    fine_paid = models.BooleanField(_("Fine Paid"), default=False)
    planned_refund = models.DecimalField(_("Planned Refund Amount"), max_digits=15, decimal_places=2, default=0)
    paid_refund = models.DecimalField(_("Paid Refund Amount"), max_digits=15, decimal_places=2, default=0)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Terminated Contract")
        verbose_name_plural = _("Terminated Contracts")

    def __str__(self):
        return f"Termination - {self.contract}"


class TerminateContractPayment(models.Model):
    termination = models.ForeignKey(TerminateContract, on_delete=models.CASCADE, related_name='refund_payments')
    payment_date = models.DateField(_("Payment Date"))
    amount = models.DecimalField(_("Payment Amount"), max_digits=15, decimal_places=2)
    payment_type = models.CharField(_("Payment Type"), max_length=20, choices=PaymentLog.PAYMENT_TYPE_CHOICES, default=PaymentLog.PAYMENT_TYPE_CASH)
    transaction_id = models.CharField(_("Transaction ID"), max_length=255, blank=True)
    notes = models.TextField(_("Notes"), blank=True)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("Termination Payment")
        verbose_name_plural = _("Termination Payments")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update termination paid refund
        total_refund_paid = sum(p.amount for p in self.termination.refund_payments.all())
        self.termination.paid_refund = total_refund_paid
        self.termination.save(update_fields=['paid_refund', 'updated_at'])



class PaymentRecord(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='payment_records')
    month_number = models.PositiveIntegerField(_("Month Number"))
    due_date = models.DateField(_("Due Date"))
    plan_amount = models.DecimalField(_("Planned Amount"), max_digits=15, decimal_places=2)
    paid_amount = models.DecimalField(_("Paid Amount"), max_digits=15, decimal_places=2, default=0)
    debt = models.DecimalField(_("Debt"), max_digits=15, decimal_places=2, default=0)
    excess_amount = models.DecimalField(_("Excess / Overpayment"), max_digits=15, decimal_places=2, default=0)
    is_debt_saved_to_next_month = models.BooleanField(_("Debt Carried Over"), default=False)
    is_late = models.BooleanField(_("Is Late"), default=False)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Payment Record")
        verbose_name_plural = _("Payment Records")
        ordering = ['contract', 'month_number']

    @property
    def status(self):
        """Dynamic calculated status: PAID, PARTIAL, OVERDUE, PENDING"""
        if self.debt <= Decimal('0.00'):
            return 'PAID'
        elif self.paid_amount > Decimal('0.00'):
            return 'PARTIAL'
        elif self.due_date < timezone.now().date():
            return 'OVERDUE'
        return 'PENDING'

    def __str__(self):
        return f"{self.contract} - Month {self.month_number}"


# --- SIGNALS ---


@receiver(post_save, sender=Contract)
def generate_payment_records(sender, instance, created, **kwargs):
    if created:
        M = instance.payment_months or 0  # Intermediate monthly installment count
        total = instance.total_amount
        dp = instance.down_payment_amount or Decimal(0)
        lp = instance.last_payment_amount or Decimal(0)

        records = []
        has_dp = (dp > 0)
        has_lp = (lp > 0)

        # Calculate intermediate pool
        intermediate_pool = total
        if has_dp:
            intermediate_pool -= dp
        if has_lp:
            intermediate_pool -= lp
        if intermediate_pool < 0:
            intermediate_pool = Decimal(0)

        # Base monthly for M intermediate installments
        if M > 0:
            base_monthly = (intermediate_pool / Decimal(M)).quantize(Decimal('0.01'))
            allocated = base_monthly * Decimal(M)
            remainder = intermediate_pool - allocated
        else:
            base_monthly = Decimal(0)
            remainder = intermediate_pool

        month_counter = 1
        date_offset_months = 0
        
        # 1. Month 1: Down Payment (if provided)
        if has_dp:
            records.append(PaymentRecord(
                contract=instance,
                month_number=month_counter,
                due_date=instance.down_payment_date or instance.contract_date,
                plan_amount=dp,
                debt=dp
            ))
            month_counter += 1
            if not instance.down_payment_date:
                date_offset_months += 1

        # 2. Intermediate Monthly Installments (M months)
        for i in range(1, M + 1):
            due_date = instance.contract_date + relativedelta(months=date_offset_months)
            planned = base_monthly
            # If no last payment, add integer remainder to the last intermediate month
            if i == M and not has_lp:
                planned += remainder

            records.append(PaymentRecord(
                contract=instance,
                month_number=month_counter,
                due_date=due_date,
                plan_amount=planned,
                debt=planned
            ))
            month_counter += 1
            date_offset_months += 1

        # 3. Final Month: Last Payment (if provided)
        if has_lp:
            due_date = instance.contract_date + relativedelta(months=date_offset_months)
            planned = lp + (remainder if M > 0 else Decimal(0))
            records.append(PaymentRecord(
                contract=instance,
                month_number=month_counter,
                due_date=due_date,
                plan_amount=planned,
                debt=planned
            ))

        # Fallback if no records created
        if not records:
            records.append(PaymentRecord(
                contract=instance,
                month_number=1,
                due_date=instance.contract_date,
                plan_amount=total,
                debt=total
            ))

        PaymentRecord.objects.bulk_create(records)


def recalculate_contract_debt(contract):
    """
    Pure Per-Row Calendar Ledger (Historical Data Mode).

    Step 1 — Receipt assignment:
        Each PaymentLog is matched to the PaymentRecord whose due_date shares
        the same calendar year+month as log.date_paid (fallback: nearest due_date).
        Uses .update() — never .save() — to avoid signal recursion.

    Step 2 — Per-row balance (self-contained, strict physical cash matching):
        paid_amount  = sum of attached PaymentLog amounts for this record
        debt         = max(0, plan_amount - paid_amount)
        excess_amount= max(0, paid_amount - plan_amount)
        Invariant:   paid_amount == plan_amount - debt + excess_amount  (always true)
    """
    all_logs = list(contract.payment_logs.all().order_by('date_paid', 'id'))
    records = list(contract.payment_records.all().order_by('month_number'))
    if not records:
        return

    # ── Step 1: Assign each PaymentLog to its calendar-month PaymentRecord ──
    for log in all_logs:
        log_date = log.date_paid.date() if hasattr(log.date_paid, 'date') else log.date_paid

        # Primary: same year + month
        target = next(
            (r for r in records
             if r.due_date.year == log_date.year and r.due_date.month == log_date.month),
            None,
        )
        # Fallback: nearest due_date
        if not target:
            target = min(records, key=lambda r: abs((r.due_date - log_date).days))

        if target and log.payment_record_id != target.id:
            PaymentLog.objects.filter(pk=log.pk).update(payment_record=target)

    # Re-fetch after FK updates so payment_record_id reflects new values
    all_logs = list(contract.payment_logs.all().order_by('date_paid', 'id'))

    # Build receipt-total map: record.id → total cash received in that row
    receipt_totals: dict = {}
    for log in all_logs:
        receipt_totals[log.payment_record_id] = (
            receipt_totals.get(log.payment_record_id, Decimal('0.00')) + log.amount
        )

    # ── Step 2: Per-row strict historical balance ──
    for record in records:
        paid = receipt_totals.get(record.id, Decimal('0.00'))
        record.paid_amount   = paid
        record.debt          = max(Decimal('0.00'), record.plan_amount - paid)
        record.excess_amount = max(Decimal('0.00'), paid - record.plan_amount)
        record.save(update_fields=['paid_amount', 'debt', 'excess_amount', 'updated_at'])


@receiver(post_save, sender=PaymentLog)
def on_payment_log_created(sender, instance, created, **kwargs):
    recalculate_contract_debt(instance.contract)


@receiver(post_delete, sender=PaymentLog)
def on_payment_log_deleted(sender, instance, **kwargs):
    recalculate_contract_debt(instance.contract)


class ContractTemplate(models.Model):
    company = models.ForeignKey('users.CustomUser', on_delete=models.CASCADE, related_name='contract_templates')
    name = models.CharField(_("Template Name"), max_length=255)
    file = models.FileField(_("Template File (.docx)"), upload_to='contract_templates/')
    content_html = models.TextField(_("HTML Content"), blank=True)
    is_default = models.BooleanField(_("Is Default"), default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Contract Template")
        verbose_name_plural = _("Contract Templates")
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.name} ({self.company})"

    def save(self, *args, **kwargs):
        if self.is_default:
            # Unset other defaults for this company
            ContractTemplate.objects.filter(company=self.company, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)



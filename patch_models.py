with open('contract/models.py', 'r') as f:
    content = f.read()

new_models = """

# ==========================================
# TERMINATION & REFUNDS
# ==========================================

class ContractTermination(models.Model):
    contract = models.OneToOneField(Contract, on_delete=models.CASCADE, related_name='termination')
    termination_date = models.DateField(_("Termination Date"), default=timezone.now)
    reason = models.TextField(_("Reason for Termination"))
    
    fine_amount = models.DecimalField(_("Fine Amount (Penalty)"), max_digits=15, decimal_places=2, default=0)
    refund_planned = models.DecimalField(_("Refund Owed to Customer"), max_digits=15, decimal_places=2, default=0)
    refund_paid_so_far = models.DecimalField(_("Refund Paid So Far"), max_digits=15, decimal_places=2, default=0)
    
    is_settled = models.BooleanField(_("Is Refund Settled"), default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _("Contract Termination")
        verbose_name_plural = _("Contract Terminations")
        
    def __str__(self):
        return f"Termination of {self.contract}"


class ContractTerminationRefund(models.Model):
    termination = models.ForeignKey(ContractTermination, on_delete=models.CASCADE, related_name='refunds')
    amount = models.DecimalField(_("Refund Amount"), max_digits=15, decimal_places=2)
    payment_date = models.DateField(_("Payment Date"), default=timezone.now)
    payment_method = models.CharField(_("Payment Method"), max_length=20, choices=PaymentLog.PAYMENT_TYPE_CHOICES, default=PaymentLog.PAYMENT_TYPE_CASH)
    receipt_image = models.ImageField(_("Receipt Image"), upload_to='refund_receipts/', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _("Termination Refund Payment")
        verbose_name_plural = _("Termination Refund Payments")
        ordering = ['-payment_date', '-created_at']
        
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self.termination.refund_paid_so_far += self.amount
            if self.termination.refund_paid_so_far >= self.termination.refund_planned:
                self.termination.is_settled = True
            self.termination.save(update_fields=['refund_paid_so_far', 'is_settled'])
            
    def __str__(self):
        return f"{self.amount} refund for {self.termination.contract}"
"""

with open('contract/models.py', 'a') as f:
    f.write(new_models)
print("Models appended.")

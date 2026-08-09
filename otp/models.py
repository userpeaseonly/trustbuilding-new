import random
import string
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta
from phonenumber_field.modelfields import PhoneNumberField

class OTPToken(models.Model):
    phone_number = PhoneNumberField(_("Phone Number"))
    code = models.CharField(_("OTP Code"), max_length=6)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    expires_at = models.DateTimeField(_("Expires At"))
    is_verified = models.BooleanField(_("Is Verified"), default=False)
    
    class Meta:
        verbose_name = _("OTP Token")
        verbose_name_plural = _("OTP Tokens")
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.phone_number} - {self.code}"

    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.code:
                self.code = ''.join(random.choices(string.digits, k=6))
            if not self.expires_at:
                self.expires_at = timezone.now() + timedelta(minutes=5)
        super().save(*args, **kwargs)
        
    def is_valid(self):
        return not self.is_verified and self.expires_at > timezone.now()

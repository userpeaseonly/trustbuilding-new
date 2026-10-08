from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

from .managers import CustomUserManager


class CustomUser(AbstractUser):
    username = None
    phone_number = PhoneNumberField(_("Phone number"), unique=True)
    secondary_phone_number = PhoneNumberField(_("Secondary phone number"), blank=True, null=True)
    full_name = models.CharField(_("Full name"), max_length=255, blank=True)
    
    GENDER_CHOICES = [
        ('M', _('Male')),
        ('F', _('Female')),
    ]
    gender = models.CharField(_('Gender'), max_length=1, choices=GENDER_CHOICES, blank=True)
    
    profile_picture = models.ImageField(_("Profile Picture"), upload_to='profile_pictures/', blank=True, null=True)
    
    # Roles
    is_company = models.BooleanField(_("Is Company"), default=False)
    is_customer = models.BooleanField(_("Is Customer"), default=False)
    is_staff_member = models.BooleanField(_("Is Staff Member"), default=False)
    
    # Identity / Passport Details
    passport_series = models.CharField(_("Passport Series"), max_length=10, blank=True)
    passport_jshshr = models.CharField(_("Passport JSHSHR (PINFL)"), max_length=14, blank=True)
    passport_issued_by = models.CharField(_("Passport Issued By"), max_length=255, blank=True)
    passport_date_of_issue = models.DateField(_("Passport Date of Issue"), null=True, blank=True)
    passport_scan = models.ImageField(_("Passport Scan"), upload_to='passport_scans/', blank=True, null=True)
    
    status = models.BooleanField(_("Status"), default=True)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    def __str__(self):
        return self.full_name if self.full_name else str(self.phone_number)

    @property
    def short_name(self):
        if not self.full_name:
            return ""
        parts = self.full_name.strip().split()
        if len(parts) == 0:
            return ""
        if len(parts) == 1:
            return parts[0]
            
        filtered_parts = []
        for part in parts:
            w = part.lower().replace("'", "").replace("‘", "").replace("’", "")
            if w not in ["ogli", "ugli", "qizi", "ўғли", "угли", "қизи", "кизи"]:
                filtered_parts.append(part)
                
        if not filtered_parts:
            filtered_parts = parts
            
        last_name = filtered_parts[0]
        initials = [f"{part[0].upper()}." for part in filtered_parts[1:] if part]
        return f"{''.join(initials)} {last_name}".strip()
class CompanyProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='company_profile')
    company_name = models.CharField(_("Company Name"), max_length=255)
    director_name = models.CharField(_("Director Full Name"), max_length=255, blank=True, help_text=_("e.g. Arslanov Axror Jamolovich"))
    director_short_name = models.CharField(_("Director Short Name"), max_length=100, blank=True, help_text=_("e.g. A.J.Arslanov"))
    inn = models.CharField(_("INN"), max_length=20, blank=True)
    address = models.TextField(_("Company Address"), blank=True)
    
    bank_name = models.CharField(_("Bank Name & Branch"), max_length=255, blank=True)
    mfo = models.CharField(_("MFO"), max_length=10, blank=True)
    account_number = models.CharField(_("Account Number (x/r)"), max_length=50, blank=True)
    jshshr = models.CharField(_("PINFL (JSHSHR)"), max_length=14, blank=True)
    
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Company Profile")
        verbose_name_plural = _("Company Profiles")

    def __str__(self):
        return self.company_name


class Role(models.Model):
    company = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='company_roles', limit_choices_to={'is_company': True})
    name = models.CharField(_("Role Name"), max_length=255)
    permissions = models.JSONField(_("Permissions"), default=list, blank=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("Role")
        verbose_name_plural = _("Roles")
        unique_together = ('company', 'name')

    def __str__(self):
        return self.name


class StaffProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='staff_profile')
    company = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='company_staff_members', limit_choices_to={'is_company': True})
    position = models.CharField(_("Position"), max_length=255, blank=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True, related_name='staff_members')
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("Staff Profile")
        verbose_name_plural = _("Staff Profiles")

    def __str__(self):
        return f"{self.user.full_name or self.user.phone_number} ({self.company})"


class SMSLog(models.Model):
    company = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sms_logs', null=True, blank=True, limit_choices_to={'is_company': True})
    phone_number = models.CharField(max_length=20)
    message = models.TextField()
    status = models.CharField(max_length=20, default='SENT')
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    parts = models.IntegerField(default=1)
    operator = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.phone_number} - {self.cost} UZS"

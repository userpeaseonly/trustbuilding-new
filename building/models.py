from django.db import models
from django.utils.translation import gettext_lazy as _
from users.models import CustomUser

class Building(models.Model):
    company = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='buildings', limit_choices_to={'is_company': True})
    assigned_staff = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_buildings', limit_choices_to={'is_staff_member': True})
    name = models.CharField(_("Building Name / Number"), max_length=255)
    block_number = models.CharField(_("Block Number"), max_length=255, blank=True)
    address = models.TextField(_("Address"), blank=True)
    floor_count = models.PositiveIntegerField(_("Floor Count"), default=1)
    entrance_count = models.PositiveIntegerField(_("Entrance Count"), default=1)
    apartment_count = models.PositiveIntegerField(_("Apartment Count"), default=1)
    
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Building")
        verbose_name_plural = _("Buildings")

    def __str__(self):
        return f"{self.name} {('- Block ' + self.block_number) if self.block_number else ''}"


class Apartment(models.Model):
    STATUS_AVAILABLE = 'AVAILABLE'
    STATUS_SOLD = 'SOLD'
    STATUS_RESERVED = 'RESERVED'

    STATUS_CHOICES = [
        (STATUS_AVAILABLE, _('Available')),
        (STATUS_SOLD, _('Sold')),
        (STATUS_RESERVED, _('Reserved')),
    ]

    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='apartments')
    apartment_number = models.CharField(_("Apartment Number"), max_length=50)
    floor_number = models.PositiveIntegerField(_("Floor Number"))
    entrance_number = models.PositiveIntegerField(_("Entrance Number"))
    living_room_count = models.PositiveIntegerField(_("Living Room Count"), default=1)
    
    total_area = models.DecimalField(_("Total Area (m2)"), max_digits=10, decimal_places=2)
    living_area = models.DecimalField(_("Living Area (m2)"), max_digits=10, decimal_places=2)
    balcony_area = models.DecimalField(_("Balcony Area (m2)"), max_digits=10, decimal_places=2, default=0)
    
    plan_image = models.ImageField(_("Floor Plan Image"), upload_to='apartment_plans/', blank=True, null=True)
    
    is_real = models.BooleanField(_("Is Real (Active)"), default=True, help_text=_("Set to False if cloned/archived for a terminated contract."))
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)
    
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Apartment")
        verbose_name_plural = _("Apartments")
        ordering = ['entrance_number', 'floor_number', 'apartment_number']

    def __str__(self):
        return f"Apt {self.apartment_number} ({self.building.name})"

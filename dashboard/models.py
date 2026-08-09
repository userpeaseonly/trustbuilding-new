from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import time


class DashboardSettings(models.Model):
    """Dashboard configuration settings - should only have one instance"""
    
    schedule_start_time = models.TimeField(
        _("Schedule Start Time"),
        default=time(8, 30),
        help_text=_("Start time for the schedule timeline (e.g., 08:30)")
    )
    
    schedule_end_time = models.TimeField(
        _("Schedule End Time"),
        default=time(20, 0),
        help_text=_("End time for the schedule timeline (e.g., 20:00)")
    )
    
    time_slot_minutes = models.PositiveIntegerField(
        _("Time Slot Duration (minutes)"),
        default=30,
        validators=[MinValueValidator(15), MaxValueValidator(120)],
        help_text=_("Duration of each time slot in minutes (15-120)")
    )
    
    updated_at = models.DateTimeField(_("Last Updated"), auto_now=True)
    
    class Meta:
        verbose_name = _("Dashboard Settings")
        verbose_name_plural = _("Dashboard Settings")
    
    def __str__(self):
        return f"Dashboard Settings (Updated: {self.updated_at})"
    
    def save(self, *args, **kwargs):
        """Ensure only one instance exists"""
        if not self.pk and DashboardSettings.objects.exists():
            # If trying to create a new instance and one already exists, update the existing one
            existing = DashboardSettings.objects.first()
            self.pk = existing.pk
        super().save(*args, **kwargs)
    
    @classmethod
    def get_settings(cls):
        """Get or create settings instance"""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings

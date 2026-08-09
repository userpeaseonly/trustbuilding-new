from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import DashboardSettings


@admin.register(DashboardSettings)
class DashboardSettingsAdmin(admin.ModelAdmin):
    """Admin interface for Dashboard Settings"""
    
    list_display = ['schedule_start_time', 'schedule_end_time', 'time_slot_minutes', 'updated_at']
    
    fieldsets = (
        (_('Schedule Timeline Settings'), {
            'fields': ('schedule_start_time', 'schedule_end_time', 'time_slot_minutes'),
            'description': _('Configure the time range and slot duration for the dashboard schedule view.')
        }),
    )
    
    def has_add_permission(self, request):
        """Only allow one settings instance"""
        return not DashboardSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of settings"""
        return False

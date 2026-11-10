from django.contrib import admin
from .models import LeadRequest


@admin.register(LeadRequest)
class LeadRequestAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone_number', 'company_name', 'apartments_count', 'preferred_language', 'status', 'telegram_notified', 'created_at')
    list_filter = ('status', 'apartments_count', 'preferred_language', 'telegram_notified', 'created_at')
    list_editable = ('status',)
    search_fields = ('full_name', 'phone_number', 'company_name', 'notes')
    readonly_fields = ('created_at', 'updated_at', 'ip_address', 'telegram_notified')
    ordering = ('-created_at',)

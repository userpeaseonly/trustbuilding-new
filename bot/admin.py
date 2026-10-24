from django.contrib import admin
from .models import TelegramReportSubscriber


@admin.register(TelegramReportSubscriber)
class TelegramReportSubscriberAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'company', 'chat_id', 'report_level', 'is_active', 'receive_morning_report', 'receive_evening_report', 'created_at')
    list_filter = ('company', 'report_level', 'is_active', 'receive_morning_report', 'receive_evening_report')
    search_fields = ('full_name', 'phone_number', 'chat_id', 'telegram_username', 'company__phone_number')

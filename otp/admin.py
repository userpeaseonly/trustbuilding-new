from django.contrib import admin
from .models import OTPToken

@admin.register(OTPToken)
class OTPTokenAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'code', 'created_at', 'expires_at', 'is_verified')
    list_filter = ('is_verified', 'created_at')
    search_fields = ('phone_number', 'code')
    readonly_fields = ('created_at',)

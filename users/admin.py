from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from hijack.contrib.admin import HijackUserAdminMixin

from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser, CompanyProfile


class CustomUserAdmin(HijackUserAdminMixin, UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    list_display = ("phone_number", "full_name", "is_company", "is_customer", "is_staff", "is_active")
    list_filter = ("is_staff", "is_active", "is_company", "is_customer", "gender", "created_at")
    fieldsets = (
        (None, {"fields": ("phone_number", "secondary_phone_number", "password")}),
        (_("Personal info"), {"fields": ("full_name", "gender", "profile_picture")}),
        (_("Roles"), {"fields": ("is_company", "is_customer")}),
        (_("Identity / Passport"), {"fields": ("passport_series", "passport_jshshr", "passport_issued_by", "passport_date_of_issue", "passport_scan")}),
        (_("Permissions"), {"fields": ("is_staff", "is_active", "is_superuser", "status", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "phone_number", "password1", "password2", "full_name", "gender",
                "is_company", "is_customer", "is_staff", "is_active", "status",
                "groups", "user_permissions"
            )}
        ),
    )
    search_fields = ("phone_number", "full_name", "passport_jshshr")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("company_name", "inn", "user")
    search_fields = ("company_name", "inn", "user__phone_number")
    fields = (
        "user", "company_name", "director_name", "director_short_name",
        "inn", "address", "bank_name", "mfo", "account_number", "jshshr",
        "created_at", "updated_at"
    )
    readonly_fields = ("created_at", "updated_at")


admin.site.register(CustomUser, CustomUserAdmin)


from .models import SMSLog

@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "status", "cost", "parts", "operator", "created_at", "company")
    list_filter = ("status", "operator", "created_at")
    search_fields = ("phone_number", "message")
    readonly_fields = ("company", "phone_number", "message", "status", "cost", "parts", "operator", "created_at")
    date_hierarchy = 'created_at'
    
    def has_add_permission(self, request):
        return False
        
    def has_change_permission(self, request, obj=None):
        return False

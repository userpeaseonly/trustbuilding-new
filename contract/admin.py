from django.contrib import admin
from .models import Contract, PaymentRecord, PaymentLog

class PaymentRecordInline(admin.TabularInline):
    model = PaymentRecord
    extra = 0
    readonly_fields = ('month_number', 'due_date', 'plan_amount', 'paid_amount', 'debt')
    can_delete = False

class PaymentLogInline(admin.TabularInline):
    model = PaymentLog
    extra = 1

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'apartment', 'company', 'contract_date', 'status', 'total_amount')
    list_filter = ('status', 'company')
    search_fields = ('customer__phone_number', 'apartment__apartment_number')
    readonly_fields = ('total_amount',)
    inlines = [PaymentRecordInline, PaymentLogInline]

@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ('contract', 'month_number', 'due_date', 'plan_amount', 'paid_amount', 'debt')
    list_filter = ('due_date',)
    search_fields = ('contract__customer__phone_number',)

@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    list_display = ('contract', 'amount', 'payment_type', 'date_paid')
    list_filter = ('payment_type', 'date_paid')
    search_fields = ('contract__customer__phone_number',)

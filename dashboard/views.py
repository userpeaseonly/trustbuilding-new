from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.utils import timezone
from contract.models import Contract, PaymentRecord, PaymentLog
from building.models import Apartment
from building.views import get_user_company

@login_required
def home(request):
    """Main KPI Dashboard for the Company"""
    # If the user is a customer, redirect to a customer view (to be built later)
    if request.user.is_customer:
        return redirect('contract:list')  # Temporary fallback for customers
    elif not (request.user.is_company or getattr(request.user, 'is_staff_member', False)):
        return redirect('users:login')
        
    company = get_user_company(request.user)
    
    now = timezone.now()
    current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # 1. Inventory Stats
    total_apartments = Apartment.objects.filter(building__company=company, is_real=True).count()
    sold_apartments = Apartment.objects.filter(building__company=company, is_real=True, status='SOLD').count()
    inventory_sold_percent = int((sold_apartments / total_apartments * 100)) if total_apartments > 0 else 0
    
    # 2. Contract Stats
    active_contracts = Contract.objects.filter(company=company, status='ACTIVE')
    active_contracts_count = active_contracts.count()
    
    # 3. Revenue Stats
    # Revenue this month (sum of all PaymentLogs this month)
    monthly_revenue = PaymentLog.objects.filter(
        contract__company=company,
        date_paid__gte=current_month
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    # Total outstanding debt (sum of all debt across active contracts)
    total_outstanding_debt = PaymentRecord.objects.filter(
        contract__company=company,
        contract__status='ACTIVE'
    ).aggregate(total=Sum('debt'))['total'] or 0
    
    # Late payments count (debt > 0 and due_date < today)
    late_payments_count = PaymentRecord.objects.filter(
        contract__company=company,
        contract__status='ACTIVE',
        debt__gt=0,
        due_date__lt=now.date()
    ).count()
    
    # Recent Payments Feed
    recent_payments = PaymentLog.objects.filter(
        contract__company=company
    ).select_related('contract__customer', 'contract__apartment').order_by('-date_paid')[:10]

    context = {
        
        'stats': {
            'total_apartments': total_apartments,
            'sold_apartments': sold_apartments,
            'inventory_sold_percent': inventory_sold_percent,
            'active_contracts_count': active_contracts_count,
            'monthly_revenue': monthly_revenue,
            'total_outstanding_debt': total_outstanding_debt,
            'late_payments_count': late_payments_count,
        },
        'recent_payments': recent_payments,
    }
    
    return render(request, 'dashboard/home.html', context)


@login_required
def topbar_search(request):
    """Global topbar search placeholder."""
    query = request.GET.get('q', '').strip()
    return render(request, 'partials/topbar_search_results.html', {
        'query': query,
        'results': [],
    })

@login_required
def sms_usage_view(request):
    """View to show SMS usage and calculated costs"""
    if not (request.user.is_company or getattr(request.user, 'is_staff_member', False)):
        return redirect('users:login')
        
    company = get_user_company(request.user)
    
    # Needs users.models.SMSLog
    from users.models import SMSLog
    
    # Calculate this month's stats
    now = timezone.now()
    current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    sms_logs = SMSLog.objects.filter(company=company).order_by('-created_at')
    
    this_month_logs = sms_logs.filter(created_at__gte=current_month)
    monthly_cost = this_month_logs.aggregate(total=Sum('cost'))['total'] or 0
    monthly_count = this_month_logs.count()
    
    all_time_cost = sms_logs.aggregate(total=Sum('cost'))['total'] or 0
    all_time_count = sms_logs.count()
    
    # Breakdown by operator (this month)
    operator_stats = this_month_logs.values('operator').annotate(
        count=Count('id'),
        total_cost=Sum('cost')
    ).order_by('-count')
    
    context = {
        'sms_logs': sms_logs[:50], # Last 50 messages
        'monthly_cost': monthly_cost,
        'monthly_count': monthly_count,
        'all_time_cost': all_time_cost,
        'all_time_count': all_time_count,
        'operator_stats': operator_stats,
    }
    
    return render(request, 'dashboard/sms_usage.html', context)

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.utils import timezone
from contract.models import Contract, PaymentRecord, PaymentLog
from building.models import Apartment

@login_required
def home(request):
    """Main KPI Dashboard for the Company"""
    # If the user is a customer, redirect to a customer view (to be built later)
    if not request.user.is_company:
        return redirect('contract:list')  # Temporary fallback for customers
        
    now = timezone.now()
    current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # 1. Inventory Stats
    total_apartments = Apartment.objects.filter(building__company=request.user, is_real=True).count()
    sold_apartments = Apartment.objects.filter(building__company=request.user, is_real=True, status='SOLD').count()
    inventory_sold_percent = int((sold_apartments / total_apartments * 100)) if total_apartments > 0 else 0
    
    # 2. Contract Stats
    active_contracts = Contract.objects.filter(company=request.user, status='ACTIVE')
    active_contracts_count = active_contracts.count()
    
    # 3. Revenue Stats
    # Revenue this month (sum of all PaymentLogs this month)
    monthly_revenue = PaymentLog.objects.filter(
        contract__company=request.user,
        date_paid__gte=current_month
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    # Total outstanding debt (sum of all debt across active contracts)
    total_outstanding_debt = PaymentRecord.objects.filter(
        contract__company=request.user,
        contract__status='ACTIVE'
    ).aggregate(total=Sum('debt'))['total'] or 0
    
    # Late payments count (debt > 0 and due_date < today)
    late_payments_count = PaymentRecord.objects.filter(
        contract__company=request.user,
        contract__status='ACTIVE',
        debt__gt=0,
        due_date__lt=now.date()
    ).count()
    
    # Recent Payments Feed
    recent_payments = PaymentLog.objects.filter(
        contract__company=request.user
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

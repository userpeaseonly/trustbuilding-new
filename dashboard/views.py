import datetime
from django.utils.dateparse import parse_date
from django.http import HttpResponse

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.utils import timezone
from contract.models import Contract, PaymentRecord, PaymentLog
from building.models import Apartment
from building.views import get_user_company
from users.permissions import require_permission

@login_required
@require_permission('view_reports')
def home(request):
    """Main KPI Dashboard for the Company"""
    # If the user is a customer, redirect to a customer view (to be built later)
    if request.user.is_customer:
        return redirect('contract:list')
    elif not (request.user.is_company or getattr(request.user, 'is_staff_member', False)):
        return redirect('users:login')
        
    company = get_user_company(request.user)
    
    # Check date filters
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    filter_all = request.GET.get('filter_all') == 'true'
    
    now = timezone.now()
    import calendar
    from decimal import Decimal
    from django.utils.dateparse import parse_date
    import datetime
    
    start_date = None
    end_date = None
    
    if not filter_all and start_date_str and end_date_str:
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        
    # Helper to apply date filters
    def apply_date_filter(qs, field_name, is_datetime=False):
        if start_date and end_date:
            kwargs = {f"{field_name}__gte": start_date}
            if is_datetime:
                # include the whole end day
                end_dt = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))
                kwargs[f"{field_name}__lte"] = end_dt
            else:
                kwargs[f"{field_name}__lte"] = end_date
            return qs.filter(**kwargs)
        return qs

    # 1. Inventory Stats
    total_apartments = Apartment.objects.filter(building__company=company, is_real=True).count()
    
    sold_apts_qs = Apartment.objects.filter(building__company=company, is_real=True, status='SOLD')
    if start_date and end_date:
        sold_apts_qs = sold_apts_qs.filter(
            contracts__status='ACTIVE',
            contracts__date_made__gte=start_date,
            contracts__date_made__lte=end_date
        ).distinct()
    sold_apartments = sold_apts_qs.count()
    inventory_sold_percent = int((sold_apartments / total_apartments * 100)) if total_apartments > 0 else 0
    
    # 2. Contract Stats
    active_contracts_qs = Contract.objects.filter(company=company, status='ACTIVE')
    active_contracts_qs = apply_date_filter(active_contracts_qs, 'date_made')
    active_contracts_count = active_contracts_qs.count()
    
    # 3. Revenue Stats
    # Expected Payment
    expected_qs = PaymentRecord.objects.filter(
        contract__company=company,
        contract__status='ACTIVE'
    )
    expected_qs = apply_date_filter(expected_qs, 'due_date')
    expected_monthly_payment = expected_qs.aggregate(total=Sum('plan_amount'))['total'] or Decimal('0.00')

    # Revenue
    revenue_qs = PaymentLog.objects.filter(contract__company=company)
    revenue_qs = apply_date_filter(revenue_qs, 'date_paid', is_datetime=True)
    monthly_revenue = revenue_qs.aggregate(total=Sum('amount'))['total'] or 0

    # Collections by type
    total_cash_collected = revenue_qs.filter(payment_type=PaymentLog.PAYMENT_TYPE_CASH).aggregate(total=Sum('amount'))['total'] or 0
    total_bank_collected = revenue_qs.filter(payment_type=PaymentLog.PAYMENT_TYPE_BANK).aggregate(total=Sum('amount'))['total'] or 0
    total_card_collected = revenue_qs.filter(payment_type=PaymentLog.PAYMENT_TYPE_CARD).aggregate(total=Sum('amount'))['total'] or 0
    total_material_collected = revenue_qs.filter(payment_type=PaymentLog.PAYMENT_TYPE_MATERIAL).aggregate(total=Sum('amount'))['total'] or 0
    
    # Total square meters sold
    total_sqm_sold = sold_apts_qs.aggregate(total=Sum('total_area'))['total'] or 0
    
    # Total outstanding debt
    debt_qs = PaymentRecord.objects.filter(
        contract__company=company,
        contract__status='ACTIVE'
    )
    debt_qs = apply_date_filter(debt_qs, 'due_date')
    total_outstanding_debt = debt_qs.aggregate(total=Sum('debt'))['total'] or 0
    
    # Late payments count (debt > 0 and due_date < today)
    late_payments_qs = PaymentRecord.objects.filter(
        contract__company=company,
        contract__status='ACTIVE',
        debt__gt=0,
        due_date__lt=now.date()
    )
    late_payments_qs = apply_date_filter(late_payments_qs, 'due_date')
    late_payments_count = late_payments_qs.count()
    
    # Recent Payments Feed
    payments_list = PaymentLog.objects.filter(
        contract__company=company
    ).select_related('contract__customer', 'contract__apartment').order_by('-date_paid')
    
    payments_list = apply_date_filter(payments_list, 'date_paid', is_datetime=True)
    

    # Export to Excel feature for Payments (Receipts)
    if request.GET.get('export') == 'excel':
        import openpyxl
        from openpyxl.styles import Font, Alignment
        from django.utils.translation import gettext as _
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Payments"
        
        headers = [
            str(_('Contract ID')),
            str(_('Customer')),
            str(_('Apartment')),
            str(_('Payment Type')),
            str(_('Amount (UZS)')),
            str(_('Date Paid'))
        ]
        ws.append(headers)
        
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center', vertical='center')
            
        for log in payments_list:
            ws.append([
                log.contract.contract_id,
                log.contract.customer.full_name or str(log.contract.customer.phone_number),
                f"Apt {log.contract.apartment.apartment_number}",
                log.get_payment_type_display(),
                float(log.amount),
                log.date_paid.strftime("%d.%m.%Y")
            ])
            
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        # Determine filename based on filter
        filename = "Payments_All.xlsx"
        if not filter_all and start_date and end_date:
            filename = f"Payments_{start_date}_to_{end_date}.xlsx"
            
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response

    from django.core.paginator import Paginator

    paginator = Paginator(payments_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'start_date_str': start_date_str if not filter_all else '',
        'end_date_str': end_date_str if not filter_all else '',
        'filter_all': filter_all,
        'stats': {
            'total_apartments': total_apartments,
            'sold_apartments': sold_apartments,
            'inventory_sold_percent': inventory_sold_percent,
            'active_contracts_count': active_contracts_count,
            'total_sqm_sold': total_sqm_sold,
            'monthly_revenue': monthly_revenue,
            'expected_monthly_payment': expected_monthly_payment,
            'total_cash_collected': total_cash_collected,
            'total_bank_collected': total_bank_collected,
            'total_card_collected': total_card_collected,
            'total_material_collected': total_material_collected,
            'total_outstanding_debt': total_outstanding_debt,
            'late_payments_count': late_payments_count,
        },
        'page_obj': page_obj,
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
@require_permission('view_sms')
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

    # Paginate sms_logs

    # Export to Excel feature for Payments (Receipts)
    if request.GET.get('export') == 'excel':
        import openpyxl
        from openpyxl.styles import Font, Alignment
        from django.utils.translation import gettext as _
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Payments"
        
        headers = [
            str(_('Contract ID')),
            str(_('Customer')),
            str(_('Apartment')),
            str(_('Payment Type')),
            str(_('Amount (UZS)')),
            str(_('Date Paid'))
        ]
        ws.append(headers)
        
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center', vertical='center')
            
        for log in payments_list:
            ws.append([
                log.contract.contract_id,
                log.contract.customer.full_name or str(log.contract.customer.phone_number),
                f"Apt {log.contract.apartment.apartment_number}",
                log.get_payment_type_display(),
                float(log.amount),
                log.date_paid.strftime("%d.%m.%Y")
            ])
            
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        # Determine filename based on filter
        filename = "Payments_All.xlsx"
        if not filter_all and start_date and end_date:
            filename = f"Payments_{start_date}_to_{end_date}.xlsx"
            
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response

    from django.core.paginator import Paginator

    paginator = Paginator(sms_logs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'paginator': paginator,
        'monthly_cost': monthly_cost,
        'monthly_count': monthly_count,
        'all_time_cost': all_time_cost,
        'all_time_count': all_time_count,
        'operator_stats': operator_stats,
    }
    
    return render(request, 'dashboard/sms_usage.html', context)

@login_required
@require_permission('view_reports')
def reconciliation_report(request):
    company = get_user_company(request.user)
    
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    now = timezone.now()
    if start_date_str and end_date_str:
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
    else:
        # Default to current month
        start_date = now.date().replace(day=1)
        end_date = now.date()

    contracts = Contract.objects.filter(
        company=company,
        status__in=[Contract.STATUS_ACTIVE, Contract.STATUS_COMPLETED]
    ).select_related('customer', 'apartment', 'apartment__building').prefetch_related(
        'payment_records', 'payment_logs'
    )

    report_data = []
    total_debt = 0
    total_overpayment = 0

    for contract in contracts:
        records = contract.payment_records.all()
        logs = contract.payment_logs.all()
        
        # 1. Past Expected & Past Paid (Before start_date)
        past_expected = sum(r.plan_amount for r in records if r.due_date < start_date)
        past_paid = sum(l.amount for l in logs if l.date_paid.date() < start_date)
        
        begin_balance = past_expected - past_paid
        
        # 2. Period Expected & Period Paid
        period_expected = sum(r.plan_amount for r in records if start_date <= r.due_date <= end_date)
        period_paid = sum(l.amount for l in logs if start_date <= l.date_paid.date() <= end_date)
        
        # 3. Ending Balance
        end_balance = begin_balance + period_expected - period_paid
        
        # Calculate monthly installment generic (find standard month amount)
        monthly_payment = 0
        if len(records) > 1:
            monthly_payment = records[1].plan_amount if len(records) > 1 else records[0].plan_amount
        elif len(records) == 1:
            monthly_payment = records[0].plan_amount
            
        report_data.append({
            'contract': contract,
            'begin_balance': begin_balance,
            'period_expected': period_expected,
            'period_paid': period_paid,
            'end_balance': end_balance,
            'monthly_payment': monthly_payment,
        })
        
        if end_balance > 0:
            total_debt += end_balance
        elif end_balance < 0:
            total_overpayment += end_balance

    # Export to Excel feature
    if request.GET.get('export') == 'excel':
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill
        from django.utils.translation import gettext as _
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Reconciliation"
        
        # Header setup
        headers = [
            str(_('Customer (FIO)')),
            str(_('Beginning Balance')),
            str(_('Expected Payment')),
            str(_('Actual Payment')),
            str(_('Ending Balance')),
            str(_('Contract No.')),
            str(_('Schedule Start Date')),
            str(_('Price per 1 m²')),
            str(_('Monthly Installment')),
        ]
        ws.append(headers)
        
        # Header formatting
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            
        for row in report_data:
            c = row['contract']
            fio = f"{c.customer.full_name or ''} - ({c.customer.phone_number}) - №{c.contract_id}"
            
            ws.append([
                fio,
                float(row['begin_balance']),
                float(row['period_expected']),
                float(row['period_paid']),
                float(row['end_balance']),
                c.contract_id,
                c.contract_date.strftime("%d.%m.%Y") if c.contract_date else "",
                float(c.price_per_square),
                float(row['monthly_payment']),
            ])
            
        # Add Totals row
        total_row = [
            str(_("OVERPAYMENT")),
            "", "", "", float(total_overpayment), "", "", "", ""
        ]
        ws.append(total_row)
        debt_row = [
            str(_("DEBT")),
            "", "", "", float(total_debt), "", "", "", ""
        ]
        ws.append(debt_row)
            
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="Reconciliation_{start_date}_to_{end_date}.xlsx"'
        wb.save(response)
        return response

    context = {
        'start_date': start_date,
        'end_date': end_date,
        'report_data': report_data,
        'total_debt': total_debt,
        'total_overpayment': total_overpayment,
    }
    return render(request, 'dashboard/reconciliation.html', context)

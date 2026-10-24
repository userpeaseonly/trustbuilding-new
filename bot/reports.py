"""
Data aggregation engine for Executive Telegram Reports.
Compiles daily sales, cash collections, overdue debt, and cash desk balances.
"""
from datetime import date, timedelta
from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.utils import timezone
from contract.models import Contract, PaymentLog, PaymentRecord
from finance.models import Wallet


def format_money_uzs(amount) -> str:
    """Format UZS amount with spaces: 380 000 000 UZS"""
    if amount is None:
        return "0 UZS"
    val = int(round(float(amount)))
    return f"{val:,}".replace(",", " ") + " UZS"


def format_compact_uzs(amount) -> str:
    """Format compact UZS: 380M UZS or 1.2B UZS"""
    if amount is None:
        return "0 UZS"
    val = float(amount)
    if abs(val) >= 1_000_000_000:
        return f"{val / 1_000_000_000:.1f} mlrd UZS".replace(".0", "")
    elif abs(val) >= 1_000_000:
        return f"{val / 1_000_000:.1f} mln UZS".replace(".0", "")
    val_int = int(round(val))
    return f"{val_int:,}".replace(",", " ") + " UZS"


def format_money_usd(amount) -> str:
    """Format USD: $140,000"""
    if amount is None:
        return "$0"
    val = int(round(float(amount)))
    return f"${val:,}"


def compile_executive_report_data(company, target_date=None) -> dict:
    """
    Compile all high-level operational and financial KPIs for a company on a given date.
    """
    if target_date is None:
        target_date = timezone.localdate()

    # 1. Today's Contracted Sales
    contracts_today = Contract.objects.filter(
        company=company,
        date_made=target_date,
        status='ACTIVE'
    ).select_related('apartment__building', 'customer')

    sales_count = contracts_today.count()
    total_sales_uzs = contracts_today.aggregate(t=Sum('total_amount'))['t'] or Decimal('0.00')

    # Building breakdown for today's sales
    building_counts = {}
    for c in contracts_today:
        b_name = c.apartment.building.name if c.apartment and c.apartment.building else "Noma'lum bino"
        building_counts[b_name] = building_counts.get(b_name, 0) + 1

    # 2. Today's Cash Inflow (Payment Logs)
    payments_today = PaymentLog.objects.filter(
        contract__company=company,
        date_paid__date=target_date
    )
    total_inflow = payments_today.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    cash_inflow = payments_today.filter(payment_type=PaymentLog.PAYMENT_TYPE_CASH).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    bank_inflow = payments_today.filter(payment_type=PaymentLog.PAYMENT_TYPE_BANK).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    card_inflow = payments_today.filter(payment_type=PaymentLog.PAYMENT_TYPE_CARD).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    material_inflow = payments_today.filter(payment_type=PaymentLog.PAYMENT_TYPE_MATERIAL).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    # 3. Expected Payments Today
    expected_records = PaymentRecord.objects.filter(
        contract__company=company,
        contract__status='ACTIVE',
        due_date=target_date,
        debt__gt=0
    )
    expected_today_count = expected_records.count()
    expected_today_amount = expected_records.aggregate(t=Sum('debt'))['t'] or Decimal('0.00')

    # 4. Overdue Debtors Alert (> 15 days late)
    overdue_threshold = target_date - timedelta(days=15)
    overdue_records = PaymentRecord.objects.filter(
        contract__company=company,
        contract__status='ACTIVE',
        due_date__lt=overdue_threshold,
        debt__gt=0
    ).select_related('contract__customer')

    overdue_buyers_count = overdue_records.values('contract__customer').distinct().count()
    total_overdue_debt = overdue_records.aggregate(t=Sum('debt'))['t'] or Decimal('0.00')

    # 5. Live Cash Desk & Bank Balances (Wallets)
    wallets = Wallet.objects.filter(company=company, is_active=True)
    wallet_balances = []
    total_kassa_uzs = Decimal('0.00')
    total_kassa_usd = Decimal('0.00')

    for w in wallets:
        bal = w.current_balance
        wallet_balances.append({
            'name': w.name,
            'type': w.wallet_type,
            'currency': w.currency,
            'balance': bal,
        })
        if w.currency == 'UZS':
            total_kassa_uzs += bal
        elif w.currency == 'USD':
            total_kassa_usd += bal

    company_name = getattr(company, 'company_profile', None)
    display_company = company_name.company_name if company_name else str(company.phone_number)

    return {
        'company_name': display_company,
        'date': target_date,
        'sales_count': sales_count,
        'total_sales_uzs': total_sales_uzs,
        'building_counts': building_counts,
        'total_inflow': total_inflow,
        'cash_inflow': cash_inflow,
        'bank_inflow': bank_inflow,
        'card_inflow': card_inflow,
        'material_inflow': material_inflow,
        'expected_today_count': expected_today_count,
        'expected_today_amount': expected_today_amount,
        'overdue_buyers_count': overdue_buyers_count,
        'total_overdue_debt': total_overdue_debt,
        'wallet_balances': wallet_balances,
        'total_kassa_uzs': total_kassa_uzs,
        'total_kassa_usd': total_kassa_usd,
    }


def build_morning_report_text(data: dict, report_level: str = 'FULL_EXECUTIVE') -> str:
    """
    09:00 AM Kickoff briefing: focuses on starting balances, expectations for today, and overdue debts.
    """
    date_str = data['date'].strftime("%d.%m.%Y")
    lines = [
        f"☀️ <b>TONGI BRIFING (09:00)</b>",
        f"🏢 <b>{data['company_name']}</b> — {date_str}\n"
    ]

    # Kassa Balances (Executive & Finance)
    if report_level in ('FULL_EXECUTIVE', 'FINANCE_ONLY'):
        lines.append("🏦 <b>TONGI KASSA VA HISOB RAQAMLAR:</b>")
        if data['wallet_balances']:
            for w in data['wallet_balances']:
                if w['currency'] == 'USD':
                    bal_str = format_money_usd(w['balance'])
                else:
                    bal_str = format_money_uzs(w['balance'])
                lines.append(f"• {w['name']}: <b>{bal_str}</b>")
            if data['total_kassa_uzs'] > 0:
                lines.append(f"👉 <i>Jami likvid UZS: {format_compact_uzs(data['total_kassa_uzs'])}</i>")
        else:
            lines.append("• <i>Kassalar kiritilmagan</i>")
        lines.append("")

    # Today's Expected Payments
    lines.append("📅 <b>BUGUN REJALASHTIRILGAN TUSHUMLAR:</b>")
    if data['expected_today_count'] > 0:
        lines.append(
            f"• Kutilayotgan to'lovlar: <b>{data['expected_today_count']} ta mijoz</b> "
            f"({format_compact_uzs(data['expected_today_amount'])})"
        )
    else:
        lines.append("• Bugun uchun rejalashtirilgan to'lovlar yo'q.")
    lines.append("")

    # Overdue Alert (> 15 days)
    lines.append("⚠️ <b>KECHIKKAN QARZDORLIK (>15 kun):</b>")
    if data['overdue_buyers_count'] > 0:
        lines.append(
            f"• <b>{data['overdue_buyers_count']} nafar xaridor</b> to'lovni kechiktirmoqda\n"
            f"• Jami qarz miqdori: <b>{format_compact_uzs(data['total_overdue_debt'])}</b>"
        )
    else:
        lines.append("• 15 kundan ortiq kechikkan qarzlar mavjud emas. Hammasi joyida! ✅")

    return "\n".join(lines)


def build_evening_report_text(data: dict, report_level: str = 'FULL_EXECUTIVE') -> str:
    """
    20:00 PM Closing Report: focuses on sales completed today, actual cash collected, and closing balances.
    """
    date_str = data['date'].strftime("%d.%m.%Y")
    lines = [
        f"🌙 <b>KUNLIK YAKUNIY HISOBOT (20:00)</b>",
        f"🏢 <b>{data['company_name']}</b> — {date_str}\n"
    ]

    # Today's Sales (Executive & Sales)
    if report_level in ('FULL_EXECUTIVE', 'SALES_ONLY'):
        lines.append("🏢 <b>BUGUNGI SAVDO:</b>")
        if data['sales_count'] > 0:
            lines.append(f"• Tuzilgan shartnomalar: <b>{data['sales_count']} ta xonadon</b>")
            if data['total_sales_uzs'] > 0:
                lines.append(f"• Jami savdo qiymati: <b>{format_money_uzs(data['total_sales_uzs'])}</b> ({format_compact_uzs(data['total_sales_uzs'])})")

            if data['building_counts']:
                b_str = ", ".join([f"{k} ({v})" for k, v in data['building_counts'].items()])
                lines.append(f"• Obyektlar: <i>{b_str}</i>")
        else:
            lines.append("• Bugun yangi shartnoma tuzilmadi.")
        lines.append("")

    # Cash Inflows (Executive, Finance & Sales)
    lines.append("💵 <b>BUGUN YIG'ILGAN TUSHUM:</b>")
    if data['total_inflow'] > 0:
        lines.append(f"• <b>Jami tushum: {format_money_uzs(data['total_inflow'])}</b> ({format_compact_uzs(data['total_inflow'])})")
        breakdown = []
        if data['cash_inflow'] > 0:
            breakdown.append(f"  ├ Naqd: {format_money_uzs(data['cash_inflow'])}")
        if data['bank_inflow'] > 0:
            breakdown.append(f"  ├ Bank: {format_money_uzs(data['bank_inflow'])}")
        if data['card_inflow'] > 0:
            breakdown.append(f"  ├ Karta: {format_money_uzs(data['card_inflow'])}")
        if data['material_inflow'] > 0:
            breakdown.append(f"  └ Barter/Material: {format_money_uzs(data['material_inflow'])}")
        if breakdown:
            lines.extend(breakdown)
    else:
        lines.append("• Bugun tushum qayd etilmadi.")
    lines.append("")

    # Balances (Executive & Finance)
    if report_level in ('FULL_EXECUTIVE', 'FINANCE_ONLY'):
        lines.append("🏦 <b>KUN OXIRIDAGI KASSA HOLATI:</b>")
        if data['wallet_balances']:
            for w in data['wallet_balances']:
                if w['currency'] == 'USD':
                    bal_str = format_money_usd(w['balance'])
                else:
                    bal_str = format_money_uzs(w['balance'])
                lines.append(f"• {w['name']}: <b>{bal_str}</b>")
        else:
            lines.append("• <i>Kassalar mavjud emas</i>")
        lines.append("")

    # Overdue Alert Summary
    if data['overdue_buyers_count'] > 0:
        lines.append(
            f"⚠️ <b>Qarzdorlik holati (>15 kun):</b> "
            f"<b>{data['overdue_buyers_count']} ta mijoz</b> "
            f"({format_compact_uzs(data['total_overdue_debt'])})"
        )

    return "\n".join(lines)

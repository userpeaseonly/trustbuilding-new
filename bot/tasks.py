"""
Celery tasks for scheduled and event-driven Telegram notifications.
- 09:00 AM: Morning Briefing
- 20:00 PM: Evening Closing Summary
- Real-time: Instant deal notification
"""
import logging
from celery import shared_task
from django.utils import timezone
from .models import TelegramReportSubscriber
from .reports import compile_executive_report_data, build_morning_report_text, build_evening_report_text, format_money_usd, format_compact_uzs
from .services import send_telegram_message, get_main_menu_keyboard

logger = logging.getLogger(__name__)


@shared_task
def send_morning_executive_reports():
    """
    Scheduled at 09:00 AM daily.
    Sends starting balances, expected incoming payments, and overdue debtors.
    """
    today = timezone.localdate()
    subscribers = TelegramReportSubscriber.objects.filter(
        is_active=True,
        receive_morning_report=True
    ).select_related('company')

    if not subscribers.exists():
        return "No active morning subscribers found."

    # Group by company to avoid re-compiling metrics multiple times
    company_data_cache = {}
    sent_count = 0

    for sub in subscribers:
        company = sub.company
        if company.id not in company_data_cache:
            company_data_cache[company.id] = compile_executive_report_data(company, target_date=today)
        
        data = company_data_cache[company.id]
        message = build_morning_report_text(data, report_level=sub.report_level)
        
        success = send_telegram_message(sub.chat_id, message, reply_markup=get_main_menu_keyboard())
        if success:
            sent_count += 1

    return f"Morning reports sent successfully: {sent_count}/{subscribers.count()}"


@shared_task
def send_evening_executive_reports():
    """
    Scheduled at 20:00 PM daily.
    Sends today's sales, cash collected by type, and closing balances.
    """
    today = timezone.localdate()
    subscribers = TelegramReportSubscriber.objects.filter(
        is_active=True,
        receive_evening_report=True
    ).select_related('company')

    if not subscribers.exists():
        return "No active evening subscribers found."

    company_data_cache = {}
    sent_count = 0

    for sub in subscribers:
        company = sub.company
        if company.id not in company_data_cache:
            company_data_cache[company.id] = compile_executive_report_data(company, target_date=today)
        
        data = company_data_cache[company.id]
        message = build_evening_report_text(data, report_level=sub.report_level)
        
        success = send_telegram_message(sub.chat_id, message, reply_markup=get_main_menu_keyboard())
        if success:
            sent_count += 1

    return f"Evening reports sent successfully: {sent_count}/{subscribers.count()}"


@shared_task
def send_instant_deal_alert(contract_id: int):
    """
    Optional real-time alert dispatched immediately when a new contract is signed.
    """
    from contract.models import Contract
    try:
        contract = Contract.objects.select_related('apartment__building', 'customer', 'company', 'staff_member').get(id=contract_id)
    except Contract.DoesNotExist:
        return "Contract not found"

    subscribers = TelegramReportSubscriber.objects.filter(
        company=contract.company,
        is_active=True,
        receive_sale_alerts=True
    )

    if not subscribers.exists():
        return "No deal alert subscribers."

    apt = contract.apartment
    bld_name = apt.building.name if apt and apt.building else "Noma'lum bino"
    apt_num = apt.apartment_number if apt else "-"
    customer_name = contract.customer.full_name or str(contract.customer.phone_number)
    manager_name = contract.staff_member.full_name if contract.staff_member else "Administrator"

    text = (
        f"🎯 <b>YANGI SHARTNOMA TUZILDI!</b>\n\n"
        f"🏢 <b>Obyekt:</b> {bld_name}, {apt_num}-xonadon\n"
        f"👤 <b>Mijoz:</b> {customer_name}\n"
        f"💰 <b>Shartnoma qiymati:</b> {format_money_usd(contract.price_in_usd)} ({format_compact_uzs(contract.total_price)})\n"
        f"👨‍💼 <b>Menejer:</b> {manager_name}\n"
        f"🕒 <b>Vaqt:</b> {timezone.localtime().strftime('%H:%M, %d.%m.%Y')}"
    )

    sent = 0
    for sub in subscribers:
        if send_telegram_message(sub.chat_id, text):
            sent += 1

    return f"Deal alert sent to {sent} subscribers."

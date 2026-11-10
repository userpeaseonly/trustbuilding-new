import os
import logging
from django.conf import settings
from bot.services import send_telegram_message
from bot.models import TelegramReportSubscriber

logger = logging.getLogger(__name__)


def notify_admin_about_new_lead(lead) -> bool:
    """
    Dispatches a Telegram notification when a new demo request is submitted on about.trust-building.uz.
    Sends to configured TELEGRAM_LEAD_CHAT_ID or verified admin subscribers.
    """
    msg_lines = [
        "🔥 <b>YANGI DEMO SOʻROVI — about.trust-building.uz</b>\n",
        f"👤 <b>Mijoz:</b> {lead.full_name}",
        f"📞 <b>Telefon:</b> <a href='tel:{lead.phone_number}'>{lead.phone_number}</a>",
        f"🏢 <b>Kompaniya:</b> {lead.company_name or 'Koʻrsatilmagan'}",
        f"🏗️ <b>Xonadonlar hajmi:</b> {lead.get_apartments_count_display() if hasattr(lead, 'get_apartments_count_display') else lead.apartments_count}",
        f"🌐 <b>Sayt tili:</b> {lead.preferred_language.upper()}",
    ]
    if lead.notes:
        msg_lines.append(f"💬 <b>Izoh:</b> {lead.notes}")

    msg_lines.append(f"\n🕒 <b>Vaqt:</b> {lead.created_at.strftime('%d.%m.%Y %H:%M')}")
    
    text = "\n".join(msg_lines)
    sent_any = False

    # 1. Check explicit environment variable (e.g. personal chat ID)
    target_chat_id = os.getenv('TELEGRAM_LEAD_CHAT_ID') or os.getenv('TELEGRAM_ADMIN_CHAT_ID')
    if target_chat_id:
        try:
            if send_telegram_message(target_chat_id, text):
                sent_any = True
                logger.info(f"New lead #{lead.id} sent to target chat ID {target_chat_id}")
        except Exception as e:
            logger.error(f"Failed to send lead to target chat ID: {e}")

    # 2. Also send to active subscribers (e.g. registered company admins / directors)
    try:
        subscribers = TelegramReportSubscriber.objects.filter(is_active=True)
        for sub in subscribers:
            if str(sub.chat_id) != str(target_chat_id):
                try:
                    if send_telegram_message(sub.chat_id, text):
                        sent_any = True
                except Exception as e:
                    logger.error(f"Failed to send lead to subscriber {sub.chat_id}: {e}")
    except Exception as e:
        logger.warning(f"Could not query Telegram subscribers: {e}")

    lead.telegram_notified = sent_any
    lead.save(update_fields=['telegram_notified'])
    return sent_any

"""
Telegram Bot service layer.
Handles Telegram API communication, message routing, and Method B user verification.
"""
import os
import re
import logging
import requests
from django.conf import settings
from django.utils import timezone
from users.models import CustomUser
from .models import TelegramReportSubscriber
from .reports import (
    compile_executive_report_data,
    build_morning_report_text,
    build_evening_report_text,
    format_money_uzs,
    format_money_usd,
    format_compact_uzs
)

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


def get_bot_token() -> str:
    """
    Retrieve active Telegram Bot token.
    Falls back gracefully between TELEGRAM_BOT_TOKEN and TELEGRAM_BACKUP_BOT_TOKEN.
    """
    backup_token = getattr(settings, 'TELEGRAM_BACKUP_BOT_TOKEN', None) or os.getenv('TELEGRAM_BACKUP_BOT_TOKEN', '')
    primary_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None) or os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    # In this environment, the backup token is the live verified @trust_buildingbot
    if backup_token:
        return backup_token
    return primary_token


def send_telegram_message(chat_id: int | str, text: str, reply_markup: dict | None = None) -> bool:
    """Send an HTML-formatted message via Telegram Bot API."""
    token = get_bot_token()
    if not token:
        logger.error("Telegram bot token not configured.")
        return False

    url = f"{TELEGRAM_API_BASE}{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup

    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if not resp.ok or not data.get('ok'):
            logger.warning(f"Telegram sendMessage failed for chat_id={chat_id}: {data}")
            return False
        return True
    except Exception as e:
        logger.error(f"Error sending Telegram message to {chat_id}: {e}")
        return False


def get_main_menu_keyboard():
    """Return persistent reply keyboard for registered users."""
    return {
        'keyboard': [
            [{'text': '📊 Bugungi hisobot'}, {'text': '🏦 Kassalar balansi'}],
            [{'text': '⚠️ Qarzdorlar ro\'yxati'}, {'text': 'ℹ️ Ma\'lumot'}]
        ],
        'resize_keyboard': True,
        'is_persistent': True
    }


def get_contact_request_keyboard():
    """Return keyboard prompting user to share contact."""
    return {
        'keyboard': [
            [{'text': '📱 Telefon raqamni yuborish', 'request_contact': True}]
        ],
        'resize_keyboard': True,
        'one_time_keyboard': True
    }


def normalize_phone_number(raw_phone: str) -> str:
    """Normalize phone number to international E.164 (+998...) format."""
    digits = re.sub(r'[^0-9]', '', str(raw_phone))
    if digits.startswith('998'):
        return f"+{digits}"
    elif len(digits) == 9:
        return f"+998{digits}"
    return f"+{digits}"


def handle_contact_verification(chat_id: int, from_user: dict, contact: dict):
    """
    Method B: Verify and identify the user via native Telegram Contact share.
    Matches phone with CustomUser in DB and binds as executive or staff.
    """
    raw_phone = contact.get('phone_number', '')
    phone_clean = normalize_phone_number(raw_phone)
    tg_username = from_user.get('username', '')
    sender_name = from_user.get('first_name', '') + (" " + from_user.get('last_name', '') if from_user.get('last_name') else '')

    # Search in database for matching active user
    matched_user = CustomUser.objects.filter(
        phone_number__endswith=phone_clean[-9:],
        is_active=True
    ).first()

    if not matched_user:
        msg = (
            f"❌ <b>Telefon raqam topilmadi!</b>\n\n"
            f"Siz yuborgan raqam: <code>{phone_clean}</code>\n"
            f"Ushbu raqam TrustBuilding tizimida ro'yxatdan o'tmagan.\n"
            f"Iltimos, kompaniya administratoriga murojaat qiling."
        )
        send_telegram_message(chat_id, msg)
        return

    # Case 1: Company Owner / CEO
    if matched_user.is_company:
        company_profile = getattr(matched_user, 'company_profile', None)
        company_name = company_profile.company_name if company_profile else "TrustBuilding"
        director_name = company_profile.director_name if company_profile and company_profile.director_name else matched_user.full_name or "Rahbar"

        subscriber, _ = TelegramReportSubscriber.objects.update_or_create(
            chat_id=chat_id,
            defaults={
                'company': matched_user,
                'user': matched_user,
                'telegram_username': tg_username,
                'full_name': director_name,
                'phone_number': phone_clean,
                'report_level': 'FULL_EXECUTIVE',
                'is_active': True,
                'receive_morning_report': True,
                'receive_evening_report': True,
            }
        )

        msg = (
            f"✅ <b>XUSH KELIBSIZ, {director_name.upper()}!</b>\n\n"
            f"Siz <b>\"{company_name}\"</b> kompaniyasi <b>Bosh rahbari / Ta'sischisi</b> sifatida muvaffaqiyatli ulandingiz.\n\n"
            f"📅 <b>Kunlik avtomatik hisobotlar:</b>\n"
            f"• 🌅 09:00 — Tongi brifing va kutilayotgan tushumlar\n"
            f"• 🌙 20:00 — Kunlik yakuniy savdo va kassa hisoboti\n\n"
            f"Istalgan vaqtda quyidagi tugmalardan foydalanishingiz mumkin:"
        )
        send_telegram_message(chat_id, msg, reply_markup=get_main_menu_keyboard())
        return

    # Case 2: Staff Member (CFO, Sales Lead, Manager)
    if getattr(matched_user, 'is_staff_member', False):
        staff_profile = getattr(matched_user, 'staff_profile', None)
        if not staff_profile or not staff_profile.company:
            send_telegram_message(chat_id, "Kechirasiz, profilingiz hech qaysi kompaniyaga biriktirilmagan.")
            return

        company = staff_profile.company
        company_profile = getattr(company, 'company_profile', None)
        company_name = company_profile.company_name if company_profile else str(company.phone_number)
        position = staff_profile.position or (staff_profile.role.name if staff_profile.role else "Xodim")

        # Determine report level based on position/role
        pos_lower = position.lower()
        if any(w in pos_lower for w in ['buxgalter', 'moliya', 'hisobchi', 'cfo']):
            report_level = 'FINANCE_ONLY'
        elif any(w in pos_lower for w in ['rop', 'sotuv', 'sales', 'menejer', 'agent']):
            report_level = 'SALES_ONLY'
        else:
            report_level = 'FULL_EXECUTIVE'

        name = matched_user.full_name or sender_name or "Xodim"

        subscriber, _ = TelegramReportSubscriber.objects.update_or_create(
            chat_id=chat_id,
            defaults={
                'company': company,
                'user': matched_user,
                'telegram_username': tg_username,
                'full_name': f"{name} ({position})",
                'phone_number': phone_clean,
                'report_level': report_level,
                'is_active': True,
                'receive_morning_report': True,
                'receive_evening_report': True,
            }
        )

        msg = (
            f"✅ <b>XUSH KELIBSIZ, {name}!</b>\n\n"
            f"Siz <b>\"{company_name}\"</b> kompaniyasining <b>{position}</b> xodimi sifatida ulandingiz.\n"
            f"Hisobot darajasi: <b>{subscriber.get_report_level_display()}</b>\n\n"
            f"Har kuni 09:00 va 20:00 da hisobotlar shu yerga yetkaziladi."
        )
        send_telegram_message(chat_id, msg, reply_markup=get_main_menu_keyboard())
        return

    # Case 3: Customer account
    send_telegram_message(
        chat_id,
        "Hurmatli mijoz! Ushbu bot faqat quruvchi kompaniya boshqaruvi va xodimlari uchun mo'ljallangan."
    )


def handle_telegram_update(update: dict):
    """Entry point for processing Telegram webhook and polling updates."""
    message = update.get('message')
    if not message:
        return

    chat = message.get('chat', {})
    chat_id = chat.get('id')
    from_user = message.get('from', {})
    text = (message.get('text') or '').strip()
    contact = message.get('contact')

    if not chat_id:
        return

    # 1. Contact Sharing (Method B identification)
    if contact:
        handle_contact_verification(chat_id, from_user, contact)
        return

    # 2. Check if chat is already registered
    subscriber = TelegramReportSubscriber.objects.filter(chat_id=chat_id, is_active=True).first()

    # /start command
    if text == '/start':
        if not subscriber:
            welcome_msg = (
                "👋 <b>Assalomu alaykum!</b>\n\n"
                "<b>TrustBuilding Executive Cockpit</b> botiga xush kelibsiz.\n\n"
                "Ushbu bot orqali har kuni <b>09:00</b> va <b>20:00</b> da kompaniyangiz savdo va kassa ko'rsatkichlari bo'yicha tezkor hisobotlarni qabul qilishingiz mumkin.\n\n"
                "Davom etish uchun pastdagi <b>«📱 Telefon raqamni yuborish»</b> tugmasini bosing:"
            )
            send_telegram_message(chat_id, welcome_msg, reply_markup=get_contact_request_keyboard())
        else:
            greeting = (
                f"Assalomu alaykum, <b>{subscriber.full_name}</b>!\n"
                f"Kompaniya: <b>{subscriber.company}</b>\n\n"
                f"Buyruqlardan foydalanishingiz mumkin:"
            )
            send_telegram_message(chat_id, greeting, reply_markup=get_main_menu_keyboard())
        return

    # If user sends any text before registering
    if not subscriber:
        prompt_msg = (
            "🔒 <b>Tizimga kirish talab etiladi.</b>\n\n"
            "Hisobotlarni qabul qilish uchun quyidagi tugmani bosib telefon raqamingizni tasdiqlang:"
        )
        send_telegram_message(chat_id, prompt_msg, reply_markup=get_contact_request_keyboard())
        return

    # 3. Interactive Commands for Registered Subscribers
    company = subscriber.company

    if text in ('/today', '📊 Bugungi hisobot'):
        data = compile_executive_report_data(company)
        report_text = build_evening_report_text(data, report_level=subscriber.report_level)
        send_telegram_message(chat_id, report_text, reply_markup=get_main_menu_keyboard())
        return

    elif text in ('/kassa', '🏦 Kassalar balansi'):
        if subscriber.report_level == 'SALES_ONLY':
            send_telegram_message(chat_id, "⚠️ Kechirasiz, sizning hisob darajangizda kassa qoldiqlari cheklangan.")
            return

        data = compile_executive_report_data(company)
        lines = [
            f"🏦 <b>{data['company_name']} KASSALAR HOLATI:</b>\n"
        ]
        if data['wallet_balances']:
            for w in data['wallet_balances']:
                if w['currency'] == 'USD':
                    b_str = format_money_usd(w['balance'])
                else:
                    b_str = format_money_uzs(w['balance'])
                lines.append(f"• {w['name']}: <b>{b_str}</b>")
            if data['total_kassa_uzs'] > 0:
                lines.append(f"\n👉 <i>Jami likvid UZS: {format_compact_uzs(data['total_kassa_uzs'])}</i>")
        else:
            lines.append("• <i>Kassalar kiritilmagan.</i>")
        send_telegram_message(chat_id, "\n".join(lines), reply_markup=get_main_menu_keyboard())
        return

    elif text in ('/qarzdorlar', '⚠️ Qarzdorlar ro\'yxati'):
        data = compile_executive_report_data(company)
        lines = [
            f"⚠️ <b>{data['company_name']} QARZDORLIK TAHLILI (>15 kun):</b>\n",
            f"• Kechikkan xaridorlar soni: <b>{data['overdue_buyers_count']} ta mijoz</b>",
            f"• Jami kechikkan summa: <b>{format_money_uzs(data['total_overdue_debt'])}</b> ({format_compact_uzs(data['total_overdue_debt'])})\n"
        ]
        send_telegram_message(chat_id, "\n".join(lines), reply_markup=get_main_menu_keyboard())
        return

    elif text in ('/info', 'ℹ️ Ma\'lumot'):
        info_text = (
            f"ℹ️ <b>PROFIL MA'LUMOTLARI:</b>\n\n"
            f"• Ism: <b>{subscriber.full_name}</b>\n"
            f"• Telefon: <code>{subscriber.phone_number}</code>\n"
            f"• Kompaniya: <b>{company}</b>\n"
            f"• Hisobot turi: <b>{subscriber.get_report_level_display()}</b>\n"
            f"• 09:00 Tongi brifing: {'✅ Faol' if subscriber.receive_morning_report else '❌ O\'chirilgan'}\n"
            f"• 20:00 Kunlik hisobot: {'✅ Faol' if subscriber.receive_evening_report else '❌ O\'chirilgan'}\n\n"
            f"Tezkor buyruqlar:\n"
            f"/today — Bugungi hisobot\n"
            f"/kassa — Kassa va bank qoldiqlari\n"
            f"/qarzdorlar — Kechikkan qarzlar"
        )
        send_telegram_message(chat_id, info_text, reply_markup=get_main_menu_keyboard())
        return

    else:
        send_telegram_message(
            chat_id,
            "Quyidagi menyu tugmalaridan birini tanlang:",
            reply_markup=get_main_menu_keyboard()
        )

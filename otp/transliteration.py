"""
Transliteration and SMS template formatting utilities.
Ensures outgoing SMS messages use pure GSM 7-bit Latin characters,
preventing UCS-2 Unicode explosion (70 chars vs 160 chars per part).
"""
import re
from datetime import date, datetime
from decimal import Decimal


CYRILLIC_TO_LATIN_MAP = {
    # Uzbek special letters
    'Ў': "O'", 'ў': "o'",
    'Ғ': "G'", 'ғ': "g'",
    'Қ': 'Q',  'қ': 'q',
    'Ҳ': 'H',  'ҳ': 'h',
    # Complex digraphs
    'Ш': 'Sh', 'ш': 'sh',
    'Ч': 'Ch', 'ч': 'ch',
    'Щ': 'Sh', 'щ': 'sh',
    'Ё': 'Yo', 'ё': 'yo',
    'Ю': 'Yu', 'ю': 'yu',
    'Я': 'Ya', 'я': 'ya',
    'Ц': 'Ts', 'ц': 'ts',
    # Standard consonants & vowels
    'А': 'A',  'а': 'a',
    'Б': 'B',  'б': 'b',
    'В': 'V',  'в': 'v',
    'Г': 'G',  'г': 'g',
    'Д': 'D',  'д': 'd',
    'Е': 'E',  'е': 'e',
    'Ж': 'J',  'ж': 'j',
    'З': 'Z',  'з': 'z',
    'И': 'I',  'и': 'i',
    'Й': 'Y',  'й': 'y',
    'К': 'K',  'к': 'k',
    'Л': 'L',  'л': 'l',
    'М': 'M',  'м': 'm',
    'Н': 'N',  'н': 'n',
    'О': 'O',  'о': 'o',
    'П': 'P',  'п': 'p',
    'Р': 'R',  'р': 'r',
    'С': 'S',  'с': 's',
    'Т': 'T',  'т': 't',
    'У': 'U',  'у': 'u',
    'Ф': 'F',  'ф': 'f',
    'Х': 'X',  'х': 'x',
    'Э': 'E',  'э': 'e',
    'Ы': 'I',  'ы': 'i',
    # Signs
    'Ъ': "'",  'ъ': "'",
    'Ь': '',   'ь': '',
}


def cyrillic_to_latin(text: str) -> str:
    """
    Transliterate Cyrillic text (Uzbek / Russian) to Latin.
    Normalizes all unicode apostrophes to ASCII 39 (').
    Preserves existing Latin characters and numbers as-is.
    """
    if not text:
        return ""
    
    # Normalize unicode apostrophes, modifier letters, and backticks to ASCII 39
    text = (
        str(text)
        .replace('‘', "'")
        .replace('’', "'")
        .replace('ʻ', "'")
        .replace('ʼ', "'")
        .replace('`', "'")
        .replace('\u00a0', ' ')  # Non-breaking space
    )
    
    result = []
    for char in text:
        result.append(CYRILLIC_TO_LATIN_MAP.get(char, char))
        
    normalized = ''.join(result)
    # Collapse multiple spaces into one
    return re.sub(r'\s+', ' ', normalized).strip()


def format_sms_amount(amount) -> str:
    """
    Format monetary amounts for SMS: whole integers separated by spaces.
    E.g. 5825000.00 -> '5 825 000'
    """
    if amount is None:
        return "0"
    try:
        val = int(round(float(amount)))
        return f"{val:,}".replace(",", " ")
    except (ValueError, TypeError):
        return str(amount)


def build_overdue_sms(customer_full_name: str, contract_id, due_date, debt_amount) -> str:
    """
    Build the Eskiz-approved Overdue Payment SMS.
    Template ID 91464:
    "Hurmatli %w{1,7} shartnomangiz bo'yicha %d kungi %w{1,5} to'lovingiz kechikmoqda. Iltimos, to'lovni amalga oshiring."
    """
    latin_name = cyrillic_to_latin(customer_full_name or 'Mijoz')
    
    if isinstance(due_date, (datetime, date)):
        due_date_str = due_date.strftime("%d.%m.%Y")
    else:
        due_date_str = str(due_date)
        
    formatted_debt = format_sms_amount(debt_amount)
    
    return (
        f"Hurmatli {latin_name}, No{contract_id} shartnomangiz bo'yicha "
        f"{due_date_str} kungi {formatted_debt} UZS to'lovingiz kechikmoqda. "
        f"Iltimos, to'lovni amalga oshiring."
    )


def build_upcoming_reminder_sms(contract_id, due_date, amount) -> str:
    """
    Build the Eskiz-approved 3-Day Upcoming Reminder SMS.
    Template ID 91465:
    "Eslatma: %w sonli shartnoma bo'yicha %d kuni %w{1,6} to'lov muddati kelmoqda."
    """
    if isinstance(due_date, (datetime, date)):
        due_date_str = due_date.strftime("%d.%m.%Y")
    else:
        due_date_str = str(due_date)
        
    formatted_amount = format_sms_amount(amount)
    
    return (
        f"Eslatma: No{contract_id} sonli shartnoma bo'yicha "
        f"{due_date_str} kuni {formatted_amount} UZS to'lov muddati kelmoqda."
    )


def build_termination_otp_sms(contract_id, otp_code: str) -> str:
    """
    Build the Eskiz-approved Contract Termination OTP SMS.
    Template ID 91463:
    "TrustBuilding: %w shartnomani bekor qilish uchun tasdiqlash kodi: %d"
    """
    return f"TrustBuilding: No{contract_id} shartnomani bekor qilish uchun tasdiqlash kodi: {otp_code}"


def build_login_otp_sms(otp_code: str) -> str:
    """
    Build the Eskiz-approved Login OTP SMS.
    Template ID 91466:
    "TrustBuilding: Tizimga kirish uchun tasdiqlash kodi: %d"
    """
    return f"TrustBuilding: Tizimga kirish uchun tasdiqlash kodi: {otp_code}"

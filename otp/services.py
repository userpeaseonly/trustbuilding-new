import requests
from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

class EskizSMS:
    """Eskiz.uz SMS Gateway Integration"""
    
    BASE_URL = 'https://notify.eskiz.uz/api'
    
    @classmethod
    def get_token(cls):
        """Retrieve token from cache or request a new one"""
        token = cache.get('eskiz_token')
        if token:
            return token
            
        try:
            response = requests.post(
                f'{cls.BASE_URL}/auth/login',
                data={
                    'email': settings.ESKIZ_EMAIL,
                    'password': settings.ESKIZ_PASSWORD
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            token = data['data']['token']
            
            # Cache token for 29 days (Eskiz token valid for 30 days)
            cache.set('eskiz_token', token, 60 * 60 * 24 * 29)
            return token
        except Exception as e:
            logger.error(f"Failed to get Eskiz token: {e}")
            return None

    @classmethod
    def calculate_sms_cost(cls, clean_phone, message):
        prefix = ""
        if clean_phone.startswith('998'):
            prefix = clean_phone[3:5]
        elif len(clean_phone) == 9:
            prefix = clean_phone[0:2]
            
        operator = "Unknown"
        price_per_part = 160 # default
        
        if prefix in ['97', '88', '87']:
            operator = "Mobiuz"
            price_per_part = 170
        elif prefix in ['90', '91', '92']:
            operator = "Beeline"
            price_per_part = 160
        elif prefix in ['93', '94', '50', '20']:
            operator = "Ucell"
            price_per_part = 160
        elif prefix in ['99', '77', '70', '95']:
            operator = "Uzmobile"
            price_per_part = 145
        elif prefix in ['33']:
            operator = "Humans"
            price_per_part = 95
        elif prefix in ['80', '98']:
            operator = "Perfectum"
            price_per_part = 110
            
        is_ucs2 = any(ord(c) > 127 for c in message)
        length = len(message)
        if is_ucs2:
            parts = 1 if length <= 70 else (length + 66) // 67
        else:
            parts = 1 if length <= 160 else (length + 152) // 153
            
        return price_per_part * parts, parts, operator

    @classmethod
    def send_sms(cls, phone_number, message, company=None):
        """Send SMS via Eskiz"""
        # Clean phone number (remove +, spaces)
        clean_phone = str(phone_number).replace('+', '').replace(' ', '')
        
        cost, parts, operator = cls.calculate_sms_cost(clean_phone, message)
        
        # --- DEVELOPMENT LOGGING ---
        print(f"\n{'='*60}")
        print(f"📨 SMS DISPATCH INTERCEPTED")
        print(f"TO: +{clean_phone} ({operator})")
        print(f"PARTS: {parts} | COST: {cost} UZS")
        print(f"MESSAGE: {message}")
        print(f"{'='*60}\n")
        logger.info(f"Attempting to send SMS to {clean_phone}: {message}")
        # ---------------------------
        
        token = cls.get_token()
        if not token:
            logger.error("Cannot send SMS: No Eskiz token available.")
            return False
            
        status = 'FAILED'
        try:
            response = requests.post(
                f'{cls.BASE_URL}/message/sms/send',
                headers={'Authorization': f'Bearer {token}'},
                data={
                    'mobile_phone': clean_phone,
                    'message': message,
                    'from': settings.ESKIZ_FROM,
                },
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"SMS sent to {clean_phone}")
            status = 'SENT'
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send SMS to {clean_phone}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Eskiz response: {e.response.text}")
            
        # Log to DB
        try:
            from users.models import SMSLog
            SMSLog.objects.create(
                company=company,
                phone_number=clean_phone,
                message=message,
                status=status,
                cost=cost if status == 'SENT' else 0.0,
                parts=parts,
                operator=operator
            )
        except Exception as log_e:
            logger.error(f"Failed to log SMS: {log_e}")
            
        return status == 'SENT'


def send_sms(phone_number, message, company=None):
    """Convenience wrapper for sending SMS via EskizSMS"""
    return EskizSMS.send_sms(phone_number, message, company)


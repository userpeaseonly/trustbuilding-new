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
    def send_sms(cls, phone_number, message):
        """Send SMS via Eskiz"""
        # Clean phone number (remove +, spaces)
        clean_phone = str(phone_number).replace('+', '').replace(' ', '')
        
        # --- DEVELOPMENT LOGGING ---
        print(f"\n{'='*60}")
        print(f"📨 SMS DISPATCH INTERCEPTED")
        print(f"TO: +{clean_phone}")
        print(f"MESSAGE: {message}")
        print(f"{'='*60}\n")
        logger.info(f"Attempting to send SMS to {clean_phone}: {message}")
        # ---------------------------
        
        token = cls.get_token()
        if not token:
            logger.error("Cannot send SMS: No Eskiz token available.")
            return False
            
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
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send SMS to {clean_phone}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Eskiz response: {e.response.text}")
            return False


def send_sms(phone_number, message):
    """Convenience wrapper for sending SMS via EskizSMS"""
    return EskizSMS.send_sms(phone_number, message)


import time
import requests
import logging
from django.core.management.base import BaseCommand
from bot.services import get_bot_token, handle_telegram_update

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run Telegram bot in long-polling mode (ideal for local testing and background worker)."

    def handle(self, *args, **options):
        token = get_bot_token()
        if not token:
            self.stderr.write(self.style.ERROR("No TELEGRAM_BOT_TOKEN or TELEGRAM_BACKUP_BOT_TOKEN configured."))
            return

        self.stdout.write(self.style.SUCCESS(f"Starting Telegram Bot Polling with token: {token[:10]}..."))
        offset = 0
        url = f"https://api.telegram.org/bot{token}/getUpdates"

        # Delete any pre-existing webhook so polling works
        try:
            del_resp = requests.post(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=5)
            self.stdout.write(f"Webhook status reset: {del_resp.json().get('description')}")
        except Exception as e:
            self.stderr.write(f"Could not delete webhook: {e}")

        while True:
            try:
                resp = requests.get(url, params={'offset': offset, 'timeout': 20}, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get('result', [])
                    for update in results:
                        update_id = update['update_id']
                        offset = max(offset, update_id + 1)
                        try:
                            handle_telegram_update(update)
                        except Exception as update_err:
                            logger.error(f"Error handling update {update_id}: {update_err}")
                else:
                    self.stderr.write(f"getUpdates returned HTTP {resp.status_code}: {resp.text}")
                    time.sleep(3)
            except requests.exceptions.RequestException as req_e:
                self.stderr.write(f"Polling connection issue: {req_e}")
                time.sleep(3)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Stopping bot polling..."))
                break

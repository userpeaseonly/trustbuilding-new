import json
import logging
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .services import handle_telegram_update

logger = logging.getLogger(__name__)


@csrf_exempt
def telegram_webhook_view(request):
    """
    Receives incoming updates from Telegram Webhook.
    """
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
        handle_telegram_update(data)
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        logger.error(f"Error processing telegram webhook: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

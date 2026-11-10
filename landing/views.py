import json
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils.translation import gettext as _
from .models import LeadRequest
from .services import notify_admin_about_new_lead


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def landing_home(request):
    """
    Renders the high-converting landing page for about.trust-building.uz
    Supports bilingual switching (O'zbekcha / Русский).
    """
    lang = request.GET.get('lang')
    if lang in ['uz', 'ru']:
        request.session['landing_lang'] = lang
    else:
        lang = request.session.get('landing_lang', 'uz')

    demo_submit_url = '/demo/' if getattr(request, 'urlconf', None) == 'landing.urls' else '/about/demo/'

    context = {
        'current_lang': lang,
        'telegram_contact': 'userpeaseonly',
        'app_login_url': 'https://trust-building.uz/dashboard/',
        'demo_submit_url': demo_submit_url,
    }
    response = render(request, 'landing/index.html', context)
    response.set_cookie('landing_lang', lang, max_age=365*24*60*60)
    return response


@require_POST
def submit_demo_request(request):
    """
    Handles demo request form submission from about.trust-building.uz.
    Accepts both standard form submissions and asynchronous fetch/JSON.
    """
    is_json = request.content_type == 'application/json'
    if is_json:
        try:
            data = json.loads(request.body)
        except Exception:
            data = {}
    else:
        data = request.POST

    full_name = data.get('full_name', '').strip()
    phone_number = data.get('phone_number', '').strip()
    company_name = data.get('company_name', '').strip()
    apartments_count = data.get('apartments_count', '50-200').strip()
    notes = data.get('notes', '').strip()
    lang = data.get('lang', request.session.get('landing_lang', 'uz'))

    # Validation
    if not full_name or not phone_number:
        err_msg = "Iltimos, ismingiz va telefon raqamingizni kiriting." if lang == 'uz' else "Пожалуйста, введите ваше имя и номер телефона."
        if is_json or request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect('landing:home')

    # Create Lead record
    lead = LeadRequest.objects.create(
        full_name=full_name,
        phone_number=phone_number,
        company_name=company_name,
        apartments_count=apartments_count,
        preferred_language=lang,
        notes=notes,
        ip_address=get_client_ip(request)
    )

    # Dispatch Telegram Notification
    notify_admin_about_new_lead(lead)

    success_msg = (
        "Rahmat! Soʻrovingiz muvaffaqiyatli qabul qilindi. Tez orada mutaxassisimiz siz bilan bogʻlanadi."
        if lang == 'uz'
        else "Спасибо! Ваша заявка успешно принята. Наш специалист свяжется с вами в ближайшее время."
    )

    if is_json or request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': success_msg,
            'lead_id': lead.id
        })

    messages.success(request, success_msg)
    return redirect('landing:home')

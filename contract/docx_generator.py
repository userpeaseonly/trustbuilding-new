import os
from django.conf import settings
from django.http import FileResponse, HttpResponse, Http404
from docxtpl import DocxTemplate
from .models import Contract
from .utils.utils import number_to_words

def generate_contract_docx_response(contract_id):
    """
    Renders and returns the official legal contract .docx document for a contract ID.
    """
    template_path = os.path.join(settings.BASE_DIR, 'contract', 'templates', 'contract', 'ShartnomaTemplate.docx')
    if not os.path.exists(template_path):
        # Fallback to legacy path if present
        legacy_path = '/home/dragonfire/Desktop/Projects/TrustBuilding/contract/templates/contract/ShartnomaTemplate.docx'
        if os.path.exists(legacy_path):
            template_path = legacy_path
        else:
            return HttpResponse("Contract template file (ShartnomaTemplate.docx) not found.", status=404)

    try:
        contract = Contract.objects.select_related(
            'customer', 'apartment', 'apartment__building', 'company'
        ).prefetch_related('payment_records').get(id=contract_id)
    except Contract.DoesNotExist:
        raise Http404("Contract not found.")

    template = DocxTemplate(template_path)

    # Down payment calculations
    down_payment = contract.down_payment_amount
    total_amount = contract.total_amount
    down_payment_pct = (down_payment / total_amount * 100) if total_amount > 0 else 0
    rest_pct = 100 - down_payment_pct

    # Table data for payment records
    table_data = [
        {
            "order": pr.month_number,
            "amount": f"{pr.plan_amount:,.2f}".replace(",", " "),
            "payment_date": pr.due_date.strftime("%d.%m.%Y")
        }
        for pr in contract.payment_records.all().order_by('month_number')
    ]

    context = {
        'customer_name': contract.customer.full_name or str(contract.customer.phone_number),
        'customer_phone': str(contract.customer.phone_number),
        'passport_series': contract.customer.passport_series,
        'passport_pinfl': contract.customer.passport_jshshr,
        'building_name': contract.apartment.building.name,
        'building_address': contract.apartment.building.address,
        'apartment_number': contract.apartment.apartment_number,
        'floor_number': contract.apartment.floor_number,
        'entrance_number': contract.apartment.entrance_number,
        'room_count': contract.apartment.living_room_count,
        'total_area': contract.apartment.total_area,
        'living_area': contract.apartment.living_area,
        'balcony_area': contract.apartment.balcony_area,
        'price_per_square': f"{contract.price_per_square:,.2f}".replace(",", " "),
        'price_per_square_words': number_to_words(contract.price_per_square),
        'contract_amount': f"{total_amount:,.2f}".replace(",", " "),
        'contract_amount_words': number_to_words(total_amount),
        'down_payment': f"{down_payment:,.2f}".replace(",", " "),
        'down_payment_words': number_to_words(down_payment),
        'last_payment': f"{contract.last_payment_amount:,.2f}".replace(",", " "),
        'last_payment_words': number_to_words(contract.last_payment_amount),
        'down_payment_percentage': f"{down_payment_pct:.2f}",
        'rest_percentage': f"{rest_pct:.2f}",
        'payment_records': table_data,
        'contract_date': contract.contract_date.strftime("%d.%m.%Y"),
        'company_name': contract.company.company_profile.company_name if hasattr(contract.company, 'company_profile') else str(contract.company),
    }

    template.render(context)

    temp_file_path = os.path.join(settings.MEDIA_ROOT, f"generated_contract_{contract_id}.docx")
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    template.save(temp_file_path)

    response = FileResponse(
        open(temp_file_path, 'rb'),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    response['Content-Disposition'] = f'attachment; filename="Shartnoma_Contract_{contract_id}.docx"'
    return response

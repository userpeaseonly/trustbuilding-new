import os
import re
from django.conf import settings
from django.http import FileResponse, HttpResponse, Http404
from docxtpl import DocxTemplate
from .models import Contract, ContractTemplate
from .utils.utils import amount_to_words_ru, MONTHS_RU

class CustomDocxTemplate(DocxTemplate):
    """Custom template that heals MS Word fragmented tags inside native Cyrillic chevrons `« »` and converts them to standard `{{ }}`"""
    def patch_xml(self, src_xml):
        KNOWN_TAGS = {
            # Cyrillic
            'Шартнома_рақами', 'Шартнома_бўлган_сана', 'Шартнома_ойи', 'Шартнома_бўлган_йил',
            'Сотиб_олувчи_ФИО', 'Шартнома_суммаси', 'Шартнома_суммаси_сўз_билан', 'Блок_',
            'Подъезд', 'Этаж', 'Квартира_рақами', 'Яшаш_хоналар_сони', 'Умумий_майдони',
            'M_1_кв_метр_нархи', 'M_1_кв_нархи_сўз_билан', 'Бошланғич_тўлов', 'График_бўйича_ойлик_тўлов',
            'Сотиб_олувчи_паспорт_серияси', 'Паспорти_берилган_вақти', 'Паспорт_берилган_жойи',
            'Телефон_рақами', 'Сотиб_олувчи_ФИО_қисқартмаси',
            
            # Latin
            'Shartnoma_raqami', 'Shartnoma_kuni', 'Shartnoma_oyi', 'Shartnoma_yili',
            'Xaridor_FIO', 'Shartnoma_summasi', 'Shartnoma_summasi_soz_bilan', 'Blok',
            'Podyezd', 'Qavat', 'Kvartira_raqami', 'Xonalar_soni', 'Umumiy_maydon',
            'Bir_kv_metr_narxi', 'Bir_kv_metr_narxi_soz_bilan', 'Boshlangich_tolov', 'Oylik_tolov',
            'Xaridor_pasporti', 'Pasport_berilgan_sana', 'Pasport_berilgan_joy',
            'Telefon_raqami', 'Xaridor_FIO_qisqa', 'Kompaniya_rahbari', 'Kompaniya_rahbari_qisqa'
        }
        
        def clean_chevron_tags(m):
            # Strip all internal XML tags so `«<w:t>Name</w:t>»` becomes `«Name»`
            clean_text = re.sub(r'<[^>]+>', '', m.group(0))
            inner_text = clean_text.replace('«', '').replace('»', '').strip()
            
            # Only convert to Jinja if it's a known placeholder
            if inner_text in KNOWN_TAGS:
                return f"{{{{ {inner_text} }}}}"
            else:
                # Leave Russian quotes alone, but we must return it with original XML?
                # Actually, m.group(0) contains the original XML which is fine to keep as-is.
                return m.group(0)
        
        # Find all `«...»` blocks safely
        src_xml = re.sub(r'«[^«»]*?»', clean_chevron_tags, src_xml, flags=re.DOTALL)
        return super().patch_xml(src_xml)

MONTHS_UZ = {
    1: 'январ', 2: 'феврал', 3: 'март', 4: 'апрел',
    5: 'май', 6: 'июн', 7: 'июл', 8: 'август',
    9: 'сентябр', 10: 'октябр', 11: 'ноябр', 12: 'декабр'
}

MONTHS_UZ_LATIN = {
    1: 'yanvar', 2: 'fevral', 3: 'mart', 4: 'aprel',
    5: 'may', 6: 'iyun', 7: 'iyul', 8: 'avgust',
    9: 'sentyabr', 10: 'oktyabr', 11: 'noyabr', 12: 'dekabr'
}

def generate_contract_docx_response(contract_id, template_id=None):
    """
    Renders and returns the official legal contract .docx document for a contract ID.
    Supports dynamic templates and native Uzbek/Russian chevron placeholders.
    """
    try:
        contract = Contract.objects.select_related(
            'customer', 'apartment', 'apartment__building', 'company'
        ).prefetch_related('payment_records').get(id=contract_id)
    except Contract.DoesNotExist:
        raise Http404("Contract not found.")

    # 1. Determine Template Path
    template_path = None
    
    if template_id:
        try:
            ct = ContractTemplate.objects.get(id=template_id, company=contract.company)
            template_path = ct.file.path
        except ContractTemplate.DoesNotExist:
            pass
            
    if not template_path:
        # Get default template for company
        ct = ContractTemplate.objects.filter(company=contract.company, is_default=True).first()
        if ct and ct.file:
            template_path = ct.file.path
            
    if not template_path:
        # Fallback to hardcoded template
        template_path = os.path.join(settings.BASE_DIR, 'contract', 'templates', 'contract', 'ShartnomaTemplate.docx')
        if not os.path.exists(template_path):
            legacy_path = '/home/dragonfire/Desktop/Projects/TrustBuilding/contract/templates/contract/ShartnomaTemplate.docx'
            if os.path.exists(legacy_path):
                template_path = legacy_path
            else:
                return HttpResponse("No contract template available. Please upload a template in settings.", status=404)

    # 2. Render Template
    template = CustomDocxTemplate(template_path)

    down_payment = contract.down_payment_amount
    total_amount = contract.total_amount
    
    # 3. Prepare Dynamic Payment Schedule
    records = contract.payment_records.all().order_by('month_number')
    monthly_payment = 0
    if len(records) > 1:
        # Usually month_number 1 is down payment, so we check month 2, or just max frequency amount
        monthly_payment = records[1].plan_amount if len(records) > 1 else records[0].plan_amount

    schedule = []
    for i, rec in enumerate(records):
        name = "Бўнак тўлови" if i == 0 else f"{i}-тўлов"
        amt = f"{rec.plan_amount:,.0f}".replace(",", " ") if rec.plan_amount else ""
        dt = rec.due_date.strftime("%d.%m.%Y") if rec.due_date else ""
        schedule.append({
            'name': name,
            'amount': amt,
            'date': dt
        })

    context = {
        # --- Native Uzbek/Russian Placeholders (Chevron format - Cyrillic) ---
        'Шартнома_рақами': str(contract.id),
        'Шартнома_бўлган_сана': str(contract.contract_date.day),
        'Шартнома_ойи': MONTHS_UZ.get(contract.contract_date.month, str(contract.contract_date.month)),
        'Шартнома_бўлган_йил': str(contract.contract_date.year),
        'Сотиб_олувчи_ФИО': contract.customer.full_name or str(contract.customer.phone_number),
        'Шартнома_суммаси': f"{total_amount:,.0f}".replace(",", " "),
        'Шартнома_суммаси_сўз_билан': amount_to_words_ru(total_amount).replace(" сумов 00 тийин, без НДС", ""),
        'Блок_': contract.apartment.building.block_number or '',
        'Подъезд': contract.apartment.entrance_number,
        'Этаж': contract.apartment.floor_number,
        'Квартира_рақами': contract.apartment.apartment_number,
        'Яшаш_хоналар_сони': contract.apartment.living_room_count,
        'Умумий_майдони': str(contract.apartment.total_area).replace('.', ','),
        'M_1_кв_метр_нархи': f"{contract.price_per_square:,.0f}".replace(",", " "),
        'M_1_кв_нархи_сўз_билан': amount_to_words_ru(contract.price_per_square).replace(" сумов 00 тийин, без НДС", ""),
        'Бошланғич_тўлов': f"{down_payment:,.0f}".replace(",", " "),
        'График_бўйича_ойлик_тўлов': f"{monthly_payment:,.0f}".replace(",", " ") if monthly_payment else "",
        'Сотиб_олувчи_паспорт_серияси': contract.customer.passport_series or '',
        'Паспорти_берилган_вақти': contract.customer.passport_given_date.strftime("%d.%m.%Y") if hasattr(contract.customer, 'passport_given_date') and contract.customer.passport_given_date else '',
        'Паспорт_берилган_жойи': getattr(contract.customer, 'passport_given_by', ''),
        'Телефон_рақами': str(contract.customer.phone_number),
        'Сотиб_олувчи_ФИО_қисқартмаси': contract.customer.full_name or '',
        
        # --- Native Uzbek Placeholders (Latin) ---
        'Shartnoma_raqami': str(contract.id),
        'Shartnoma_kuni': str(contract.contract_date.day),
        'Shartnoma_oyi': MONTHS_UZ_LATIN.get(contract.contract_date.month, str(contract.contract_date.month)),
        'Shartnoma_yili': str(contract.contract_date.year),
        'Xaridor_FIO': contract.customer.full_name or str(contract.customer.phone_number),
        'Shartnoma_summasi': f"{total_amount:,.0f}".replace(",", " "),
        'Shartnoma_summasi_soz_bilan': amount_to_words_ru(total_amount).replace(" сумов 00 тийин, без НДС", ""),
        'Blok': contract.apartment.building.block_number or '',
        'Podyezd': contract.apartment.entrance_number,
        'Qavat': contract.apartment.floor_number,
        'Kvartira_raqami': contract.apartment.apartment_number,
        'Xonalar_soni': contract.apartment.living_room_count,
        'Umumiy_maydon': str(contract.apartment.total_area).replace('.', ','),
        'Bir_kv_metr_narxi': f"{contract.price_per_square:,.0f}".replace(",", " "),
        'Bir_kv_metr_narxi_soz_bilan': amount_to_words_ru(contract.price_per_square).replace(" сумов 00 тийин, без НДС", ""),
        'Boshlangich_tolov': f"{down_payment:,.0f}".replace(",", " "),
        'Oylik_tolov': f"{monthly_payment:,.0f}".replace(",", " ") if monthly_payment else "",
        'Xaridor_pasporti': contract.customer.passport_series or '',
        'Pasport_berilgan_sana': contract.customer.passport_given_date.strftime("%d.%m.%Y") if hasattr(contract.customer, 'passport_given_date') and contract.customer.passport_given_date else '',
        'Pasport_berilgan_joy': getattr(contract.customer, 'passport_given_by', ''),
        'Xaridor_FIO_qisqa': contract.customer.full_name or '',
        'Kompaniya_rahbari': getattr(contract.company.company_profile, 'director_name', '') if hasattr(contract.company, 'company_profile') else '',
        'Kompaniya_rahbari_qisqa': getattr(contract.company.company_profile, 'director_short_name', '') if hasattr(contract.company, 'company_profile') else '',
        
        # --- Dynamic Payment Schedule ---
        'schedule': schedule,
        
        # --- English Fallbacks for old templates ---
        'contract_amount': f"{total_amount:,.2f}".replace(",", " "),
        'down_payment': f"{down_payment:,.2f}".replace(",", " "),
        'customer_name': contract.customer.full_name or str(contract.customer.phone_number),
        'building_name': contract.apartment.building.name,
        'apartment_number': contract.apartment.apartment_number,
        'contract_date': contract.contract_date.strftime("%d.%m.%Y"),
    }

    template.render(context)
    
    temp_file_path = os.path.join(settings.MEDIA_ROOT, "generated_contracts", f"generated_contract_{contract_id}.docx")
    os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
    template.save(temp_file_path)

    response = FileResponse(
        open(temp_file_path, 'rb'),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    response['Content-Disposition'] = f'attachment; filename="Shartnoma_{contract_id}.docx"'
    return response

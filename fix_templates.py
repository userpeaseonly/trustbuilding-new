import os
import django
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()

from contract.models import ContractTemplate

KNOWN_TAGS = {
    'Шартнома_рақами', 'Шартнома_бўлган_сана', 'Шартнома_ойи', 'Шартнома_бўлган_йил',
    'Сотиб_олувчи_ФИО', 'Шартнома_суммаси', 'Шартнома_суммаси_сўз_билан', 'Блок_',
    'Подъезд', 'Этаж', 'Квартира_рақами', 'Яшаш_хоналар_сони', 'Умумий_майдони',
    'M_1_кв_метр_нархи', 'M_1_кв_нархи_сўз_билан', 'Бошланғич_тўлов', 'График_бўйича_ойлик_тўлов',
    'Сотиб_олувчи_паспорт_серияси', 'Паспорти_берилган_вақти', 'Паспорт_берилган_жойи',
    'Телефон_рақами', 'Сотиб_олувчи_ФИО_қисқартмаси', 'contract_amount', 'down_payment', 'customer_name', 'building_name', 'apartment_number', 'contract_date'
}

for t in ContractTemplate.objects.all():
    if not t.content_html:
        continue
    
    html = t.content_html
    
    def replacer(match):
        content = match.group(1).strip()
        if content in KNOWN_TAGS:
            return f"{{{{ {content} }}}}"
        else:
            return f"«{content}»"
            
    # Fix instances where it's already {{ }}
    html = re.sub(r'\{\{\s*(.*?)\s*\}\}', replacer, html)
    # Fix instances where it's « »
    html = re.sub(r'«\s*(.*?)\s*»', replacer, html)
    
    t.content_html = html
    t.save()
    print(f"Fixed template {t.id}")

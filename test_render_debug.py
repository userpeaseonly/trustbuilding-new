import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()

from docxtpl import DocxTemplate
from contract.docx_generator import CustomDocxTemplate

template = CustomDocxTemplate('modified_template.docx')

context = {
    'Шартнома_суммаси': '100 000 000',
    'schedule': [
        {'name': 'Бўнак тўлови', 'amount': '20 000 000', 'date': '01.01.2024'},
    ]
}

try:
    template.render(context)
except Exception as e:
    # let's look at template.docx._part.blob
    pass
    
# But actually docxtpl has get_xml() if it was loaded.
# Wait, why was template.docx None?

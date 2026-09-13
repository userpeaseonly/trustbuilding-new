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
        {'name': '1-тўлов', 'amount': '10 000 000', 'date': '01.02.2024'},
        {'name': '2-тўлов', 'amount': '10 000 000', 'date': '01.03.2024'},
    ]
}

template.render(context)
template.save('test_rendered.docx')
print("Render successful!")

import os
import django
from docx import Document

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()

doc = Document('docs/№314.docx')

for table in doc.tables:
    try:
        header = table.rows[0].cells[1].text.strip().lower()
        if 'тўлов номи' in header:
            jami_idx = -1
            for i, row in enumerate(table.rows):
                if 'Жами' in row.cells[1].text:
                    jami_idx = i
                    break
            
            # Row 1 is {%tr for %}
            table.rows[1].cells[0].text = "{%tr for r in schedule %}"
            for c in table.rows[1].cells[1:]: c.text = ""
            
            # Row 2 is data
            table.rows[2].cells[0].text = "{{ loop.index }}"
            table.rows[2].cells[1].text = "{{ r.name }}"
            table.rows[2].cells[2].text = "{{ r.amount }}"
            table.rows[2].cells[3].text = "{{ r.date }}"
            
            # Row 3 is {%tr endfor %}
            table.rows[3].cells[0].text = "{%tr endfor %}"
            for c in table.rows[3].cells[1:]: c.text = ""
            
            # Delete rows from 4 up to jami_idx - 1
            for _ in range(4, jami_idx):
                tr = table.rows[4]._tr
                tr.getparent().remove(tr)
                
            # Now Jami row is at 4
            table.rows[4].cells[2].text = "«Шартнома_суммаси»"
            break
    except Exception as e:
        print("Err:", e)

doc.save('modified_template.docx')

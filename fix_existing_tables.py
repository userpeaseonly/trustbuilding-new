import os
import django
import io
from docx import Document

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()

from contract.models import ContractTemplate

for tmpl in ContractTemplate.objects.all():
    try:
        if not tmpl.file:
            continue
            
        doc = Document(tmpl.file.path)
        modified = False
        
        for table in doc.tables:
            try:
                header = table.rows[0].cells[1].text.strip().lower()
                if 'тўлов номи' in header or 'тўлов суммаси' in header:
                    jami_idx = -1
                    for i, row in enumerate(table.rows):
                        if len(row.cells) > 1 and 'Жами' in row.cells[1].text:
                            jami_idx = i
                            break
                    
                    if jami_idx > 4:
                        modified = True
                        table.rows[1].cells[0].text = "{%tr for r in schedule %}"
                        for c in table.rows[1].cells[1:]: c.text = ""
                        
                        table.rows[2].cells[0].text = "{{ loop.index }}"
                        table.rows[2].cells[1].text = "{{ r.name }}"
                        table.rows[2].cells[2].text = "{{ r.amount }}"
                        if len(table.rows[2].cells) > 3:
                            table.rows[2].cells[3].text = "{{ r.date }}"
                        
                        table.rows[3].cells[0].text = "{%tr endfor %}"
                        for c in table.rows[3].cells[1:]: c.text = ""
                        
                        for _ in range(4, jami_idx):
                            tr = table.rows[4]._tr
                            tr.getparent().remove(tr)
                            
                        if len(table.rows[4].cells) > 2:
                            table.rows[4].cells[2].text = "«Шартнома_суммаси»"
                        break
            except Exception:
                continue
                
        if modified:
            doc.save(tmpl.file.path)
            print(f"Fixed table in template {tmpl.id}")
    except Exception as e:
        print(f"Error {tmpl.id}: {e}")


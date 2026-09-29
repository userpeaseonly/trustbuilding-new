import docx

def fix_table_index(doc_path, output_path):
    doc = docx.Document(doc_path)
    
    for table in doc.tables:
        for row in table.rows:
            # Check if this row has the s.name variable
            if len(row.cells) >= 4 and '{{ s.name }}' in row.cells[1].text:
                if not row.cells[0].text.strip():
                    # The first cell is empty, add loop.index
                    row.cells[0].text = '{{ loop.index }}'
                    # preserve font if possible
                    for p in row.cells[0].paragraphs:
                        for run in p.runs:
                            run.font.name = 'Cambria'
                            run.font.size = docx.shared.Pt(12)

    doc.save(output_path)

fix_table_index("/tmp/bunyodkorshartnomashablon_tables_fixed.docx", "/tmp/bunyodkorshartnomashablon_index_fixed.docx")
print("Done")

import docx

doc_path = '/app/temp_template.docx'
doc = docx.Document(doc_path)

for i, para in enumerate(doc.paragraphs):
    if "___" in para.text or "«" in para.text:
        print(f"[{i}] {para.text}")


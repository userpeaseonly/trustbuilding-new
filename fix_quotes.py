import os
import django
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()

from contract.models import ContractTemplate

for t in ContractTemplate.objects.all():
    if not t.content_html:
        continue
    
    html = t.content_html
    # Remove any stray `«` or `»` or `"` immediately inside `{{` `}}`
    def fix_jinja_syntax(match):
        inner = match.group(1).replace('«', '').replace('»', '').replace('"', '').strip()
        return f"{{{{ {inner} }}}}"
        
    new_html = re.sub(r'\{\{(.*?)\}\}', fix_jinja_syntax, html)
    # Also fix where the original file actually had `« Шартнома_бўлган_сана »` instead of `«Шартнома_бўлган_сана»` maybe?
    # No, the above regex fixes existing ones. But wait, `«{{ Шартнома_бўлган_сана` -> This is `«` before `{{`. That's fine as long as `{{` itself is valid.
    
    if html != new_html:
        t.content_html = new_html
        t.save()
        print(f"Fixed template {t.id}")
        

import re

with open('contract/templates/contract/template_list.html', 'r') as f:
    content = f.read()

add_html = """
                    <div class="flex justify-between border-b border-gray-700/50 pb-1 hover:bg-gray-700/30 p-1"><span class="text-blue-300">«Kompaniya_rahbari»</span> <span class="text-gray-500 text-xs font-sans">{% trans "Company Director" %}</span></div>
                    <div class="flex justify-between border-b border-gray-700/50 pb-1 hover:bg-gray-700/30 p-1"><span class="text-blue-300">«Kompaniya_rahbari_qisqa»</span> <span class="text-gray-500 text-xs font-sans">{% trans "Director Short Name" %}</span></div>
"""

split_token = '<h4 class="font-bold text-gray-100 font-sans border-b border-gray-700 pb-1 mb-2 mt-6">{% trans "Customer Info" %}</h4>'
parts = content.split(split_token)

if len(parts) == 2:
    new_content = parts[0] + add_html + '                    ' + split_token + parts[1]
    with open('contract/templates/contract/template_list.html', 'w') as f:
        f.write(new_content)
    print("Success")
else:
    print("Could not find token")

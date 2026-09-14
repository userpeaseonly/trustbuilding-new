with open('contract/templates/contract/detail.html', 'r') as f:
    content = f.read()

old_btn = """                        <button @click="isImportModalOpen = true" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-medium transition shadow-xs inline-flex items-center gap-2">
                            📥 {% trans "Import Payments (Excel)" %}
                        </button>"""

new_btn = """                        {% if contract.status == 'ACTIVE' %}
                        <button @click="isImportModalOpen = true" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-medium transition shadow-xs inline-flex items-center gap-2">
                            📥 {% trans "Import Payments (Excel)" %}
                        </button>
                        {% endif %}"""

content = content.replace(old_btn, new_btn)

with open('contract/templates/contract/detail.html', 'w') as f:
    f.write(content)
print("Success")

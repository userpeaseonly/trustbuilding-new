with open('contract/templates/contract/termination_dashboard.html', 'r') as f:
    content = f.read()

old_btn = """        <div class="flex gap-3">
            <a href="{% url 'contract:list' %}" class="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm font-medium transition">
                {% trans "Back to Contracts" %}
            </a>
        </div>"""

new_btn = """        <div class="flex gap-3">
            <a href="{% url 'contract:detail' contract.pk %}?view=schedule" class="px-4 py-2 bg-indigo-900/50 hover:bg-indigo-800/80 text-indigo-200 border border-indigo-700 rounded-lg text-sm font-medium transition">
                📅 {% trans "View Original Schedule" %}
            </a>
            <a href="{% url 'contract:list' %}" class="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm font-medium transition">
                {% trans "Back to Contracts" %}
            </a>
        </div>"""

content = content.replace(old_btn, new_btn)

with open('contract/templates/contract/termination_dashboard.html', 'w') as f:
    f.write(content)
print("Success")

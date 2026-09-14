with open('contract/templates/contract/detail.html', 'r') as f:
    content = f.read()

old_btn = """            <a href="{% url 'contract:initiate_termination' pk=contract.pk %}" class="px-4 py-2 bg-red-900/50 hover:bg-red-800/80 text-red-200 border border-red-700 rounded-lg text-xs font-medium transition">
                🚫 {% trans "Terminate Contract" %}
            </a>"""

new_btn = """            <form action="{% url 'contract:initiate_termination' pk=contract.pk %}" method="post" class="inline">
                {% csrf_token %}
                <button type="submit" class="px-4 py-2 bg-red-900/50 hover:bg-red-800/80 text-red-200 border border-red-700 rounded-lg text-xs font-medium transition cursor-pointer">
                    🚫 {% trans "Terminate Contract" %}
                </button>
            </form>"""

content = content.replace(old_btn, new_btn)

with open('contract/templates/contract/detail.html', 'w') as f:
    f.write(content)
print("Success")

with open('contract/templates/contract/detail.html', 'r') as f:
    content = f.read()

old_block = """            {% if contract.status == 'ACTIVE' %}
            <button type="button" @click="$dispatch('open-payment-modal')" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition shadow-xs flex items-center gap-1.5">"""

new_block = """            {% if contract.status == 'TERMINATED' %}
            <a href="{% url 'contract:termination_dashboard' pk=contract.pk %}" class="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-xs font-medium transition shadow-xs flex items-center gap-1.5">
                📊 {% trans "Refund Dashboard" %}
            </a>
            {% endif %}
            
            {% if contract.status == 'ACTIVE' %}
            <button type="button" @click="$dispatch('open-payment-modal')" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition shadow-xs flex items-center gap-1.5">"""

content = content.replace(old_block, new_block)

with open('contract/templates/contract/detail.html', 'w') as f:
    f.write(content)
print("Success")

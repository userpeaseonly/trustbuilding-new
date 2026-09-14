with open('contract/templates/contract/terminated_list.html', 'r') as f:
    content = f.read()

content = content.replace('<th class="px-6 py-4">{% trans "Reason" %}</th>', '<th class="px-6 py-4">{% trans "Reason" %}</th>\n                        <th class="px-6 py-4 text-right">{% trans "Actions" %}</th>')

row_end = '<td class="px-6 py-4 text-xs text-gray-400 max-w-xs truncate">{{ term.termination_reason|default:"-" }}</td>'
row_end_new = row_end + """
                        <td class="px-6 py-4 text-right">
                            <a href="{% url 'contract:termination_dashboard' term.contract.pk %}" class="px-3 py-1.5 bg-gray-600 hover:bg-gray-500 text-white rounded text-xs font-medium transition inline-flex items-center gap-1">
                                📊 {% trans "Dashboard" %}
                            </a>
                        </td>"""
content = content.replace(row_end, row_end_new)
content = content.replace('colspan="7"', 'colspan="8"')

with open('contract/templates/contract/terminated_list.html', 'w') as f:
    f.write(content)
print("Success")

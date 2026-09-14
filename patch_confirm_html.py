with open('contract/templates/contract/confirm_termination.html', 'r') as f:
    content = f.read()

content = content.replace('<div class="max-w-xl mx-auto space-y-6 mt-8">', '<div class="max-w-xl mx-auto space-y-6 mt-8" x-data="{ fine: 0, totalPaid: {{ total_paid|default:0|stringformat:\'f\' }} }">')
content = content.replace('name="fine_amount" value="0.00"', 'name="fine_amount" x-model.number="fine"')

live_preview = """
            <div class="bg-gray-700/50 rounded-lg p-4 space-y-2 text-sm border border-gray-600">
                <div class="flex justify-between text-gray-300">
                    <span>{% trans "Total Amount Paid by Customer:" %}</span>
                    <span class="font-bold text-white">{{ total_paid|formatted_amount }} UZS</span>
                </div>
                <div class="flex justify-between text-rose-300">
                    <span>{% trans "- Fine Penalty:" %}</span>
                    <span class="font-bold" x-text="fine.toLocaleString('ru-RU') + ' UZS'"></span>
                </div>
                <div class="flex justify-between border-t border-gray-600 pt-2 text-emerald-300 font-bold">
                    <span>{% trans "= Total Refund Owed to Customer:" %}</span>
                    <span x-text="Math.max(0, totalPaid - fine).toLocaleString('ru-RU') + ' UZS'"></span>
                </div>
            </div>

            <div class="pt-4 flex justify-between items-center border-t border-gray-700">"""
            
content = content.replace('<div class="pt-4 flex justify-between items-center border-t border-gray-700">', live_preview)

with open('contract/templates/contract/confirm_termination.html', 'w') as f:
    f.write(content)
print("Success")

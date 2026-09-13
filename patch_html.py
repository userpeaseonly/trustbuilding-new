with open('contract/templates/contract/detail.html', 'r') as f:
    content = f.read()

empty_state_old = """                    {% empty %}
                    <p class="text-xs text-gray-400 italic text-center py-4">{% trans "No payments recorded yet." %}</p>"""

empty_state_new = """                    {% empty %}
                    <div class="text-center py-6 bg-gray-900/40 border border-gray-700 border-dashed rounded-lg" x-data="{ isImportModalOpen: false }">
                        <svg class="w-8 h-8 text-gray-500 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <p class="text-xs text-gray-400 italic mb-4">{% trans "No payments recorded yet." %}</p>
                        
                        <button @click="isImportModalOpen = true" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-medium transition shadow-xs inline-flex items-center gap-2">
                            📥 {% trans "Import Payments (Excel)" %}
                        </button>
                        
                        <!-- Import Modal -->
                        <div x-show="isImportModalOpen"
                             class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
                             x-transition.opacity
                             style="display: none;"
                             x-cloak>
                            <div @click.away="isImportModalOpen = false" class="bg-gray-800 rounded-2xl shadow-xl w-full max-w-md overflow-hidden ring-1 ring-gray-700 text-left">
                                <div class="px-6 py-4 border-b border-gray-700 bg-gray-800 flex justify-between items-center">
                                    <h3 class="text-sm font-bold text-white">{% trans "Import Payments" %}</h3>
                                    <button @click="isImportModalOpen = false" class="text-gray-400 hover:text-white transition">
                                        <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                                    </button>
                                </div>
                                <div class="p-6 space-y-6">
                                    
                                    <div class="bg-indigo-900/30 border border-indigo-800 rounded-xl p-4 text-center">
                                        <h4 class="text-xs font-semibold text-indigo-300 mb-1">{% trans "Step 1: Download Template" %}</h4>
                                        <p class="text-[11px] text-gray-400 mb-3">{% trans "Download the pre-formatted Excel template and fill in the payment details." %}</p>
                                        <a href="{% url 'contract:download_import_template' %}" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium transition inline-flex items-center gap-1.5 w-full justify-center">
                                            📄 {% trans "Download Template" %}
                                        </a>
                                    </div>
                                    
                                    <div class="bg-gray-900/50 border border-gray-700 rounded-xl p-4">
                                        <h4 class="text-xs font-semibold text-gray-300 mb-1 text-center">{% trans "Step 2: Upload Data" %}</h4>
                                        <p class="text-[11px] text-gray-400 mb-3 text-center">{% trans "Upload the filled Excel file." %}</p>
                                        <form action="{% url 'contract:import_payments' pk=contract.pk %}" method="post" enctype="multipart/form-data" class="space-y-4">
                                            {% csrf_token %}
                                            <input type="file" name="file" accept=".xlsx" required class="block w-full text-xs text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-600 file:text-white hover:file:bg-indigo-700 transition">
                                            <button type="submit" class="w-full px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition shadow-xs flex justify-center items-center gap-1.5">
                                                ✅ {% trans "Upload and Process" %}
                                            </button>
                                        </form>
                                    </div>
                                    
                                </div>
                            </div>
                        </div>
                    </div>"""

if empty_state_old in content:
    content = content.replace(empty_state_old, empty_state_new)
    with open('contract/templates/contract/detail.html', 'w') as f:
        f.write(content)
    print("Success")
else:
    print("Could not find empty state block")

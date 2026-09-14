with open('contract/templates/contract/detail.html', 'r') as f:
    content = f.read()

# Refactor Import Modal
old_import = """                        <!-- Import Modal -->
                        <div x-show="isImportModalOpen"
                             class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
                             x-transition.opacity
                             style="display: none;"
                             x-cloak>
                            <div @click.away="isImportModalOpen = false" class="bg-gray-800 rounded-2xl shadow-xl w-full max-w-md overflow-hidden ring-1 ring-gray-700 text-left">"""
                            
new_import = """                        <!-- Import Modal -->
                        <dialog x-ref="importModal"
                                x-init="$watch('isImportModalOpen', val => val ? $el.showModal() : $el.close())"
                                @close="isImportModalOpen = false"
                                @click="if($event.target === $el) isImportModalOpen = false"
                                class="bg-gray-800 rounded-2xl shadow-xl w-full max-w-md overflow-hidden ring-1 ring-gray-700 text-left backdrop:bg-black/60 backdrop:backdrop-blur-md m-auto p-0 text-white"
                                style="display: none;"
                                x-cloak>
                            <div class="w-full">"""
content = content.replace(old_import, new_import)

# Close tag for Import Modal
content = content.replace("""                                </div>
                            </div>
                        </div>""", """                                </div>
                            </div>
                        </dialog>""")

# Refactor Payment Modal
old_payment = """    <!-- Payment Modal -->
    <div x-data="{ isPaymentModalOpen: false }"
         @open-payment-modal.window="isPaymentModalOpen = true"
         x-show="isPaymentModalOpen" 
         class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
         x-transition.opacity
         style="display: none;"
         x-cloak>
        
        <div class="bg-gray-800 border border-gray-700 rounded-xl w-full max-w-md shadow-2xl overflow-hidden"
             @click.away="isPaymentModalOpen = false"
             x-show="isPaymentModalOpen"
             x-transition:enter="transition ease-out duration-200"
             x-transition:enter-start="opacity-0 scale-95"
             x-transition:enter-end="opacity-100 scale-100"
             x-data="{ """

new_payment = """    <!-- Payment Modal -->
    <dialog x-data="{ isPaymentModalOpen: false }"
         @open-payment-modal.window="isPaymentModalOpen = true"
         x-ref="paymentModal"
         x-init="$watch('isPaymentModalOpen', val => val ? $el.showModal() : $el.close())"
         @close="isPaymentModalOpen = false"
         @click="if($event.target === $el) isPaymentModalOpen = false"
         class="bg-gray-800 border border-gray-700 rounded-xl w-full max-w-md shadow-2xl overflow-hidden m-auto p-0 text-white backdrop:bg-black/60 backdrop:backdrop-blur-md"
         style="display: none;"
         x-cloak>
        
        <div x-data="{ """

content = content.replace(old_payment, new_payment)

# Close tag for Payment Modal
content = content.replace("""            </div>
        </div>
    </div>
{% endblock %}""", """            </div>
        </div>
    </dialog>
{% endblock %}""")


with open('contract/templates/contract/detail.html', 'w') as f:
    f.write(content)
print("Success")

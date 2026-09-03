from decimal import Decimal
from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .models import Contract, PaymentLog
from users.models import CustomUser
from building.models import Apartment

class ContractWizardForm(forms.ModelForm):
    CUSTOMER_MODE_CHOICES = [
        ('existing', _('Select Existing Customer')),
        ('new', _('Register New Customer')),
    ]
    
    customer_mode = forms.CharField(
        initial='existing',
        widget=forms.HiddenInput()
    )
    
    existing_customer = forms.ModelChoiceField(
        label=_("Select Customer"),
        queryset=CustomUser.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500'})
    )
    
    # New Customer Fields
    new_customer_phone = forms.CharField(
        label=_("Phone Number"),
        required=False,
        widget=forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm placeholder-gray-400 focus:ring-2 focus:ring-indigo-500', 'placeholder': '+998901234567'})
    )
    new_customer_name = forms.CharField(
        label=_("Full Name"),
        required=False,
        widget=forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm placeholder-gray-400 focus:ring-2 focus:ring-indigo-500', 'placeholder': _('e.g. Alisher Tursunov')})
    )
    new_customer_gender = forms.ChoiceField(
        label=_("Gender"),
        choices=[('', '----'), ('M', _('Male')), ('F', _('Female'))],
        required=False,
        widget=forms.Select(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500'})
    )
    new_customer_passport_series = forms.CharField(
        label=_("Passport Series"),
        required=False,
        widget=forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm placeholder-gray-400 focus:ring-2 focus:ring-indigo-500', 'placeholder': 'AA1234567'})
    )
    new_customer_passport_jshshr = forms.CharField(
        label=_("PINFL (JSHSHR)"),
        required=False,
        widget=forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm placeholder-gray-400 focus:ring-2 focus:ring-indigo-500', 'placeholder': '31204951820042'})
    )
    new_customer_passport_issued_by = forms.CharField(
        label=_("Passport Issued By"),
        required=False,
        widget=forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm placeholder-gray-400 focus:ring-2 focus:ring-indigo-500', 'placeholder': _('e.g. Toshkent sh. Yunusobod tuman IIB')})
    )
    new_customer_passport_date_of_issue = forms.DateField(
        label=_("Passport Date of Issue"),
        required=False,
        input_formats=['%d/%m/%Y', '%d.%m.%Y', '%Y-%m-%d'],
        widget=forms.TextInput(attrs={'class': 'datepicker-dmy w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500', 'placeholder': 'DD/MM/YYYY'})
    )
    new_customer_passport_scan = forms.ImageField(
        label=_("Passport Scan File"),
        required=False,
        widget=forms.FileInput(attrs={'class': 'w-full text-xs text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-600 file:text-white hover:file:bg-indigo-700'})
    )
    
    class Meta:
        model = Contract
        fields = ['apartment', 'contract_date', 'price_per_square', 'down_payment_amount', 'last_payment_amount', 'payment_months']
        widgets = {
            'apartment': forms.Select(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500'}),
            'contract_date': forms.TextInput(attrs={'class': 'datepicker-dmy w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500', 'placeholder': 'DD/MM/YYYY'}),
            'price_per_square': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500', 'step': '0.01', 'placeholder': '0.00'}),
            'down_payment_amount': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500', 'step': '0.01', 'placeholder': '0.00'}),
            'last_payment_amount': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500', 'step': '0.01', 'placeholder': '0.00'}),
            'payment_months': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500', 'placeholder': '12'}),
        }
        
    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        self.fields['contract_date'].input_formats = ['%d/%m/%Y', '%d.%m.%Y', '%Y-%m-%d']
        self.fields['down_payment_amount'].required = False
        self.fields['last_payment_amount'].required = False
        self.fields['existing_customer'].queryset = CustomUser.objects.filter(is_customer=True).order_by('-created_at')
        self.fields['existing_customer'].label_from_instance = lambda obj: f"{obj.full_name or 'N/A'} ({obj.phone_number}) - {obj.passport_jshshr or obj.passport_series or 'No Passport'}"
        if company:
            self.fields['apartment'].queryset = Apartment.objects.filter(
                building__company=company, 
                status='AVAILABLE', 
                is_real=True
            )

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('down_payment_amount'):
            cleaned_data['down_payment_amount'] = Decimal('0.00')
        if not cleaned_data.get('last_payment_amount'):
            cleaned_data['last_payment_amount'] = Decimal('0.00')

        mode = cleaned_data.get('customer_mode', 'existing')
        
        if mode == 'existing':
            if not cleaned_data.get('existing_customer'):
                self.add_error('existing_customer', _("Please select an existing customer from the dropdown."))
        elif mode == 'new':
            phone = cleaned_data.get('new_customer_phone')
            name = cleaned_data.get('new_customer_name')
            series = cleaned_data.get('new_customer_passport_series')
            pinfl = cleaned_data.get('new_customer_passport_jshshr')
            
            if not phone:
                self.add_error('new_customer_phone', _("Phone number is required for registering a new customer."))
            if not name:
                self.add_error('new_customer_name', _("Full name is required for registering a new customer."))
            if not series:
                self.add_error('new_customer_passport_series', _("Passport series is required for legal contract generation."))
            if not pinfl:
                self.add_error('new_customer_passport_jshshr', _("PINFL (JSHSHR) is required for legal contract generation."))
                
            if phone and CustomUser.objects.filter(phone_number=phone).exists():
                self.add_error('new_customer_phone', _("A customer with this phone number already exists. Please select 'Existing Customer' instead."))

        return cleaned_data


class PaymentLogForm(forms.ModelForm):
    date_paid = forms.DateTimeField(
        required=False,
        label=_("Payment Date (d/m/Y)"),
        input_formats=['%d/%m/%Y %H:%M', '%d/%m/%Y', '%d.%m.%Y %H:%M', '%d.%m.%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'],
        widget=forms.TextInput(attrs={
            'class': 'datepicker-dmy w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500 font-mono',
            'placeholder': 'DD/MM/YYYY'
        })
    )

    class Meta:
        model = PaymentLog
        fields = ['amount', 'payment_type', 'date_paid', 'receipt_image']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500 font-mono font-bold text-lg',
                'step': '0.01',
                'placeholder': '0.00',
                'id': 'payment-amount-input'
            }),
            'payment_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-indigo-500'
            }),
            'receipt_image': forms.FileInput(attrs={
                'class': 'w-full text-xs text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-600 file:text-white hover:file:bg-indigo-700'
            }),
        }

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise forms.ValidationError(_("Payment amount must be greater than zero."))
        return amount

    def clean_date_paid(self):
        date_paid = self.cleaned_data.get('date_paid')
        if not date_paid:
            return timezone.now()
        return date_paid

from django.contrib.auth.forms import UserCreationForm, UserChangeForm, AuthenticationForm
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import CustomUser


class PhoneAuthenticationForm(AuthenticationForm):
    """Custom authentication form using phone number instead of username"""
    username = forms.CharField(
        label=_("Phone Number"),
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'placeholder': '+998901234567',
            'autofocus': True
        })
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'placeholder': _('Enter your password')
        })
    )


class CustomUserCreationForm(UserCreationForm):

    class Meta:
        model = CustomUser
        fields = ("phone_number", "full_name", "is_company", "is_customer")


class CustomUserChangeForm(UserChangeForm):

    class Meta:
        model = CustomUser
        fields = ("phone_number", "full_name", "is_company", "is_customer", "is_staff_member")


class StaffCreationForm(forms.ModelForm):
    position = forms.CharField(label=_("Position"), max_length=255, required=False, widget=forms.TextInput(attrs={
        'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
        'placeholder': _('Sales Manager')
    }))
    
    role = forms.ModelChoiceField(
        queryset=None, 
        required=False,
        empty_label=_("No Role"),
        widget=forms.Select(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500'})
    )

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if company:
            from .models import Role
            self.fields['role'].queryset = Role.objects.filter(company=company)

    class Meta:
        model = CustomUser
        fields = ['phone_number', 'full_name', 'gender']
        widgets = {
            'phone_number': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': '+998901234567'}),
            'full_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': _('John Doe')}),
            'gender': forms.Select(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg'}),
        }


class CustomerRegistrationForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = [
            'phone_number', 'full_name', 'gender',
            'passport_series', 'passport_jshshr', 'passport_issued_by',
            'passport_date_of_issue', 'passport_scan'
        ]
        widgets = {
            'phone_number': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': '+998901234567'}),
            'full_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': _('Full Name')}),
            'gender': forms.Select(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg'}),
            'passport_series': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': _('AA1234567')}),
            'passport_jshshr': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': _('14-digit PINFL')}),
            'passport_issued_by': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': _('IIB / Police Department')}),
            'passport_date_of_issue': forms.DateInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'type': 'date'}),
            'passport_scan': forms.FileInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg'}),
        }


class RoleForm(forms.ModelForm):
    class Meta:
        from .models import Role
        model = Role
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': _('e.g. Senior Sales')}),
        }

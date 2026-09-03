from django.contrib.auth.forms import UserCreationForm, UserChangeForm, AuthenticationForm
from django import forms

from .models import CustomUser


class PhoneAuthenticationForm(AuthenticationForm):
    """Custom authentication form using phone number instead of username"""
    username = forms.CharField(
        label="Phone Number",
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'placeholder': '+998901234567',
            'autofocus': True
        })
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'placeholder': 'Enter your password'
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
    position = forms.CharField(label="Position", max_length=255, required=False, widget=forms.TextInput(attrs={
        'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
        'placeholder': 'Sales Manager'
    }))

    class Meta:
        model = CustomUser
        fields = ['phone_number', 'full_name', 'gender']
        widgets = {
            'phone_number': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': '+998901234567'}),
            'full_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': 'John Doe'}),
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
            'full_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': 'Full Name'}),
            'gender': forms.Select(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg'}),
            'passport_series': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': 'AA1234567'}),
            'passport_jshshr': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': '14-digit PINFL'}),
            'passport_issued_by': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'placeholder': 'IIB / Police Department'}),
            'passport_date_of_issue': forms.DateInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg', 'type': 'date'}),
            'passport_scan': forms.FileInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg'}),
        }


from django import forms
from django.utils.translation import gettext_lazy as _
from .models import ComplexExplorer


class ComplexExplorerForm(forms.ModelForm):
    class Meta:
        model = ComplexExplorer
        fields = ['name', 'subtitle', 'description', 'masterplan_image', 'masterplan_pdf']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': _('e.g. NUR AVENUE 2'),
            }),
            'subtitle': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': _('e.g. 5-Storey Residential Complex'),
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-3.5 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
            }),
            'masterplan_image': forms.FileInput(attrs={
                'accept': 'image/*',
                'class': 'w-full text-xs text-slate-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border file:border-indigo-100 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100',
            }),
            'masterplan_pdf': forms.FileInput(attrs={
                'accept': '.pdf,application/pdf',
                'class': 'w-full text-xs text-slate-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border file:border-emerald-100 file:text-xs file:font-semibold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100',
            }),
        }

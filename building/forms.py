from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Building, Apartment

class BuildingForm(forms.ModelForm):
    class Meta:
        model = Building
        fields = ['name', 'block_number', 'address', 'floor_count', 'entrance_count', 'apartments_per_floor']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded-lg text-slate-900 text-sm placeholder-gray-400 focus:ring-2 focus:ring-indigo-500', 'placeholder': _('e.g. Navoi Residency')}),
            'block_number': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded-lg text-slate-900 text-sm placeholder-gray-400 focus:ring-2 focus:ring-indigo-500', 'placeholder': _('e.g. Block A')}),
            'address': forms.Textarea(attrs={'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded-lg text-slate-900 text-sm placeholder-gray-400 focus:ring-2 focus:ring-indigo-500', 'rows': 2, 'placeholder': _('Full address...')}),
            'floor_count': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded-lg text-slate-900 text-sm placeholder-gray-400 focus:ring-2 focus:ring-indigo-500', 'min': 1, 'max': 100, 'x-model': 'floorCount'}),
            'entrance_count': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded-lg text-slate-900 text-sm placeholder-gray-400 focus:ring-2 focus:ring-indigo-500', 'min': 1, 'max': 20, 'x-model': 'entranceCount'}),
            'apartments_per_floor': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded-lg text-slate-900 text-sm placeholder-gray-400 focus:ring-2 focus:ring-indigo-500', 'min': 1, 'max': 20, 'x-model': 'aptsPerFloor'}),
        }

class ApartmentUpdateForm(forms.ModelForm):
    class Meta:
        model = Apartment
        fields = ['living_room_count', 'total_area', 'living_area', 'balcony_area', 'status', 'plan_image']
        widgets = {
            'living_room_count': forms.NumberInput(attrs={'class': 'w-full rounded-md border-gray-600 bg-gray-800 text-white'}),
            'total_area': forms.NumberInput(attrs={'class': 'w-full rounded-md border-gray-600 bg-gray-800 text-white', 'step': '0.01'}),
            'living_area': forms.NumberInput(attrs={'class': 'w-full rounded-md border-gray-600 bg-gray-800 text-white', 'step': '0.01'}),
            'balcony_area': forms.NumberInput(attrs={'class': 'w-full rounded-md border-gray-600 bg-gray-800 text-white', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'w-full rounded-md border-gray-600 bg-gray-800 text-white'}),
            'plan_image': forms.FileInput(attrs={'class': 'w-full text-white'}),
        }

from django.contrib import admin
from .models import Building, Apartment

@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('name', 'block_number', 'company', 'floor_count', 'entrance_count', 'apartment_count')
    list_filter = ('company',)
    search_fields = ('name', 'block_number', 'company__phone_number')

@admin.register(Apartment)
class ApartmentAdmin(admin.ModelAdmin):
    list_display = ('apartment_number', 'building', 'floor_number', 'entrance_number', 'total_area', 'status', 'is_real')
    list_filter = ('building', 'status', 'is_real')
    search_fields = ('apartment_number', 'building__name')

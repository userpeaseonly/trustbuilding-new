from django.contrib import admin
from .models import (
    ApartmentHotspot,
    BuildingExplorer,
    ComplexBuildingHotspot,
    ComplexExplorer,
    FloorExplorer,
)


@admin.register(ComplexExplorer)
class ComplexExplorerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'company', 'is_published', 'public_share_enabled', 'updated_at')
    list_filter = ('is_published', 'public_share_enabled')
    readonly_fields = ('share_token',)


@admin.register(ComplexBuildingHotspot)
class ComplexBuildingHotspotAdmin(admin.ModelAdmin):
    list_display = ('id', 'complex_explorer', 'building')


@admin.register(BuildingExplorer)
class BuildingExplorerAdmin(admin.ModelAdmin):
    list_display = ('id', 'building', 'extraction_status', 'is_published', 'public_share_enabled', 'updated_at')
    list_filter = ('extraction_status', 'is_published', 'public_share_enabled')
    readonly_fields = ('share_token',)


@admin.register(FloorExplorer)
class FloorExplorerAdmin(admin.ModelAdmin):
    list_display = ('id', 'building_explorer', 'floor_number')
    list_filter = ('floor_number',)


@admin.register(ApartmentHotspot)
class ApartmentHotspotAdmin(admin.ModelAdmin):
    list_display = ('id', 'floor_explorer', 'apartment', 'detected_label')

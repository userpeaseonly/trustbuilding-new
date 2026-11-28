import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class ComplexExplorer(models.Model):
    """Masterplan/aerial overview connecting multiple BuildingExplorers for a project."""

    company = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='complex_explorers',
        limit_choices_to={'is_company': True},
    )
    name = models.CharField(_("Complex Name"), max_length=255)
    subtitle = models.CharField(_("Subtitle"), max_length=255, blank=True)
    description = models.TextField(_("Description"), blank=True)
    masterplan_image = models.ImageField(
        _("Masterplan / Aerial Image"),
        upload_to='explorer/complexes/',
        blank=True,
        null=True,
    )
    masterplan_pdf = models.FileField(
        _("Site Masterplan PDF (Optional)"),
        upload_to='explorer/complexes/pdfs/',
        blank=True,
        null=True,
    )
    image_width = models.PositiveIntegerField(default=1600)
    image_height = models.PositiveIntegerField(default=1000)
    compass_angle = models.FloatField(_("North Azimuth (deg)"), default=0.0)
    ai_metadata = models.JSONField(default=dict, blank=True)
    is_published = models.BooleanField(_("Published"), default=False)
    public_share_enabled = models.BooleanField(_("Public Share Enabled"), default=False)
    share_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Complex Explorer")
        verbose_name_plural = _("Complex Explorers")

    def __str__(self):
        return self.name


class ComplexBuildingHotspot(models.Model):
    """Clickable block polygon rendered on a ComplexExplorer masterplan image."""

    complex_explorer = models.ForeignKey(
        ComplexExplorer,
        on_delete=models.CASCADE,
        related_name='building_hotspots',
    )
    building = models.ForeignKey(
        'building.Building',
        on_delete=models.CASCADE,
        related_name='complex_hotspots',
    )
    polygon_points = models.JSONField(default=list)
    label_x = models.FloatField(default=50.0)
    label_y = models.FloatField(default=50.0)
    ai_confidence = models.FloatField(null=True, blank=True)
    ai_notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ('complex_explorer', 'building')
        ordering = ['building__block_number', 'building__id']

    def __str__(self):
        return f"{self.complex_explorer.name} -> {self.building}"


class BuildingExplorer(models.Model):
    """Interactive presentation configuration & extracted visual assets for one Building."""

    STATUS_IDLE = 'IDLE'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_READY = 'READY'
    STATUS_FAILED = 'FAILED'

    STATUS_CHOICES = [
        (STATUS_IDLE, _('Idle')),
        (STATUS_PROCESSING, _('Processing')),
        (STATUS_READY, _('Ready')),
        (STATUS_FAILED, _('Failed')),
    ]

    building = models.OneToOneField(
        'building.Building',
        on_delete=models.CASCADE,
        related_name='explorer',
    )
    complex_explorer = models.ForeignKey(
        ComplexExplorer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='building_explorers',
    )
    source_pdf = models.FileField(
        _("Source Architectural PDF"),
        upload_to='explorer/pdfs/',
        blank=True,
        null=True,
    )
    hero_render = models.ImageField(
        _("Exterior 3D Render"),
        upload_to='explorer/renders/',
        blank=True,
        null=True,
    )
    hero_width = models.PositiveIntegerField(default=1600)
    hero_height = models.PositiveIntegerField(default=1000)
    extra_renders = models.JSONField(default=list, blank=True)
    compass_angle = models.FloatField(_("North Azimuth (deg)"), default=0.0)
    facade_faces = models.JSONField(default=list, blank=True)
    # Per-camera-angle floor bands for extra renders: {render_path: {"floors": {"1": [[x, y], ...], ...}}}.
    # The hero render keeps using FloorExplorer.facade_polygon; every other angle needs its own shapes.
    view_overlays = models.JSONField(default=dict, blank=True)
    ai_metadata = models.JSONField(default=dict, blank=True)
    atmosphere_enabled = models.BooleanField(_("Atmosphere Switcher"), default=True)
    is_published = models.BooleanField(_("Published"), default=False)
    public_share_enabled = models.BooleanField(_("Public Share Enabled"), default=False)
    share_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    extraction_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_IDLE,
    )
    extraction_summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['building__block_number', 'building__id']
        verbose_name = _("Building Explorer")
        verbose_name_plural = _("Building Explorers")

    def __str__(self):
        return f"Explorer: {self.building}"


class FloorExplorer(models.Model):
    """One floor's facade band polygon on hero_render and its cropped architectural floor plan."""

    building_explorer = models.ForeignKey(
        BuildingExplorer,
        on_delete=models.CASCADE,
        related_name='floors',
    )
    floor_number = models.PositiveIntegerField()
    facade_polygon = models.JSONField(default=list, blank=True)
    plan_image = models.ImageField(
        _("Floor Plan Image"),
        upload_to='explorer/floor_plans/',
        blank=True,
        null=True,
    )
    plan_width = models.PositiveIntegerField(default=1600)
    plan_height = models.PositiveIntegerField(default=1000)
    geometry_3d = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ('building_explorer', 'floor_number')
        ordering = ['floor_number']
        verbose_name = _("Floor Explorer")
        verbose_name_plural = _("Floor Explorers")

    def __str__(self):
        return f"{self.building_explorer.building} - Floor {self.floor_number}"


class ApartmentHotspot(models.Model):
    """Clickable SVG polygon on a FloorExplorer plan linked to a Building Apartment."""

    floor_explorer = models.ForeignKey(
        FloorExplorer,
        on_delete=models.CASCADE,
        related_name='hotspots',
    )
    apartment = models.ForeignKey(
        'building.Apartment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='explorer_hotspots',
    )
    polygon_points = models.JSONField(default=list)
    label_x = models.FloatField(default=50.0)
    label_y = models.FloatField(default=50.0)
    detected_label = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ['id']
        verbose_name = _("Apartment Hotspot")
        verbose_name_plural = _("Apartment Hotspots")

    def __str__(self):
        target = self.apartment.apartment_number if self.apartment else (self.detected_label or 'Unmapped')
        return f"Floor {self.floor_explorer.floor_number} -> Apt {target}"

import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include
from django.urls import path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from .views import health

urlpatterns = [
    path('health/', health, name='health'),
    path('', RedirectView.as_view(url='/dashboard/', permanent=False), name='root'),
    path('admin/', admin.site.urls),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API — auth & public
    # Legacy APIs removed. New endpoints will be added as needed.
    # App URLs
    path('i18n/', include('django.conf.urls.i18n')),  # Language switching
    path('dashboard/', include('dashboard.urls')),  # Dashboard app
    path('users/', include('users.urls')),  # Users app
    path('otp/', include('otp.urls')),  # OTP Auth app
    path('building/', include('building.urls')),  # Inventory app
    path('contract/', include('contract.urls')),  # Contract app
]

# Serve static and media files in development
if settings.DEBUG:
    # urlpatterns += [path("__reload__/", include("django_browser_reload.urls"))]  # Disabled: auto-reload not needed
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

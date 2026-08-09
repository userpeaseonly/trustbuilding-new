from django.urls import path

from .views import AboutUsView


urlpatterns = [
    path('', AboutUsView.as_view(), name='api-about-us'),
]

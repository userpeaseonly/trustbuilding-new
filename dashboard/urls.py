from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.topbar_search, name='topbar_search'),
    path('sms-usage/', views.sms_usage_view, name='sms_usage'),
]

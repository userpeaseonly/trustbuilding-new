from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.topbar_search, name='topbar_search'),
]

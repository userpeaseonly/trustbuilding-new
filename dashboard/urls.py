from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.topbar_search, name='topbar_search'),
    path('print/test/', views.print_test, name='print_test'),
]

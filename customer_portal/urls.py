from django.urls import path
from . import views

app_name = 'customer_portal'

urlpatterns = [
    path('', views.home, name='home'),
    path('contract/<int:contract_id>/', views.contract_detail, name='contract_detail'),
]

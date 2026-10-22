from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.finance_overview, name='overview'),
    path('transaction/add/', views.add_transaction, name='add_transaction'),
    path('transaction/<int:pk>/delete/', views.delete_transaction, name='delete_transaction'),
    path('wallets/', views.manage_wallets, name='manage_wallets'),
    path('categories/', views.manage_categories, name='manage_categories'),
    path('debtor/<int:pk>/send-sms/', views.send_debtor_reminder, name='send_debtor_reminder'),
]

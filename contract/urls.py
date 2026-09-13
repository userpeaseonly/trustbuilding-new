from django.urls import path
from . import views

app_name = 'contract'

urlpatterns = [
    path('', views.contract_list, name='list'),
    path('create/', views.contract_create, name='create'),
    path('<int:pk>/', views.contract_detail, name='detail'),
    path('<int:pk>/payment/', views.process_payment, name='process_payment'),
    path('<int:pk>/download-docx/', views.download_docx_contract, name='download_docx'),
    path('<int:pk>/download-payments/', views.download_payments_excel, name='download_payments'),
    path('<int:pk>/import-payments/', views.import_payments_excel, name='import_payments'),
    path('templates/payment-import/', views.download_import_template, name='download_import_template'),
    path('payment/<int:payment_id>/receipt/', views.receipt_view, name='receipt'),
    path('<int:pk>/initiate-termination/', views.initiate_termination, name='initiate_termination'),
    path('<int:pk>/confirm-termination/', views.confirm_termination, name='confirm_termination'),
    path('terminated/', views.terminated_contracts_list, name='terminated_list'),
    path('quick-payment/', views.staff_quick_payment, name='quick_payment'),
    path('search-customers/', views.search_customers_api, name='search_customers'),
    path('search-apartments/', views.search_apartments_api, name='search_apartments'),
    
    # Contract Templates Management
    path('templates/', views.template_list, name='template_list'),
    path('templates/create/', views.template_create, name='template_create'),
    path('templates/<int:pk>/delete/', views.template_delete, name='template_delete'),
    path('templates/<int:pk>/set-default/', views.template_set_default, name='template_set_default'),
]


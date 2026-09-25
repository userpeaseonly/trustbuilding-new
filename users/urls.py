from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Management URLs
    path('staff/', views.staff_list_view, name='staff_list'),
    path('staff/<int:pk>/edit/', views.staff_edit, name='staff_edit'),
    path('staff/<int:pk>/toggle-active/', views.staff_toggle_active, name='staff_toggle_active'),
    path('staff/<int:pk>/delete/', views.staff_delete, name='staff_delete'),
    path('customers/', views.customer_list_view, name='customer_list'),
]


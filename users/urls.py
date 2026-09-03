from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Management URLs
    path('staff/', views.staff_list_view, name='staff_list'),
    path('customers/', views.customer_list_view, name='customer_list'),
]


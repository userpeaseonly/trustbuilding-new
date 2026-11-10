from django.urls import path
from . import views

app_name = 'landing'

urlpatterns = [
    path('', views.landing_home, name='home'),
    path('demo/', views.submit_demo_request, name='submit_demo'),
]

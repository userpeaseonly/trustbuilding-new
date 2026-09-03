from django.urls import path
from . import views

app_name = 'building'

urlpatterns = [
    path('', views.building_list, name='list'),
    path('create/', views.building_create, name='create'),
    path('<int:pk>/', views.building_detail, name='detail'),
    path('<int:pk>/matrix/', views.building_matrix_view, name='matrix'),
    path('apartment/<int:pk>/update/', views.apartment_update, name='apartment_update'),
]


from django.urls import path
from . import views

app_name = 'explorer'

urlpatterns = [
    path('', views.explorer_index, name='index'),
    path('building/<int:building_pk>/', views.explorer_building_view, name='building_view'),
    path('building/<int:building_pk>/studio/', views.explorer_building_studio, name='building_studio'),
    path('complex/create/', views.explorer_complex_create, name='complex_create'),
    path('complex/<int:pk>/', views.explorer_complex_view, name='complex_view'),
    path('complex/<int:pk>/studio/', views.explorer_complex_studio, name='complex_studio'),

    # Public read-only presentation routes (requires is_published=True and public_share_enabled=True)
    path('s/building/<uuid:token>/', views.public_building_view, name='public_building_view'),
    path('s/complex/<uuid:token>/', views.public_complex_view, name='public_complex_view'),
    path(
        's/complex/<uuid:token>/building/<int:building_pk>/',
        views.public_complex_building_view,
        name='public_complex_building_view',
    ),
]

from django.urls import path
from .views import telegram_webhook_view

app_name = 'bot'

urlpatterns = [
    path('webhook/', telegram_webhook_view, name='webhook'),
]

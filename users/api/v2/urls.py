from django.urls import path
from .views import MeV2View, MyReferralsV2View

urlpatterns = [
    path('me/', MeV2View.as_view(), name='auth-me-v2'),
    path('me/referrals/', MyReferralsV2View.as_view(), name='auth-me-referrals-v2'),
]

from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login
from django.contrib import messages
from django.utils.translation import gettext as _
from django.utils import timezone
from django.urls import reverse
from users.models import CustomUser
from .models import OTPToken
from .services import EskizSMS

def request_otp_view(request):
    """View to request an OTP code"""
    if request.user.is_authenticated:
        return redirect('dashboard:home')
        
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')
        if not phone_number:
            messages.error(request, _("Phone number is required."))
            return redirect('otp:request_otp')
            
        # Optional: Rate limiting check here (e.g., max 3 active tokens per phone)
        active_tokens = OTPToken.objects.filter(
            phone_number=phone_number, 
            is_verified=False, 
            expires_at__gt=timezone.now()
        ).count()
        
        if active_tokens >= 3:
            messages.error(request, _("Too many OTP requests. Please wait."))
            return redirect('otp:request_otp')
            
        # Create token (OTPToken's save method automatically generates a 6-digit random code)
        token = OTPToken.objects.create(phone_number=phone_number)
        
        # Send SMS via Eskiz
        message = f"TrustBuilding: Tizimga kirish uchun tasdiqlash kodi: {token.code}"
        success = EskizSMS.send_sms(phone_number, message)
        
        from django.conf import settings
        if success or settings.DEBUG:  # Only fallback in DEBUG mode
            if not success:
                print(f"--- DEV MODE: SMS failed. The OTP for {phone_number} is {token.code} ---")
            # Store phone number in session for verification step
            request.session['otp_phone_number'] = str(phone_number)
            messages.success(request, _("OTP sent to your phone."))
            return redirect('otp:verify_otp')
        else:
            messages.error(request, _("Failed to send SMS. Please try again."))
            return redirect('otp:request_otp')
            
    return render(request, 'otp/request_otp.html')


def verify_otp_view(request):
    """View to verify the OTP and log the user in"""
    if request.user.is_authenticated:
        return redirect('dashboard:home')
        
    phone_number = request.session.get('otp_phone_number')
    if not phone_number:
        messages.error(request, _("Session expired. Please request a new code."))
        return redirect('otp:request_otp')
        
    if request.method == 'POST':
        code = request.POST.get('code')
        if not code:
            messages.error(request, _("Code is required."))
            return redirect('otp:verify_otp')
            
        # Find valid token
        token = OTPToken.objects.filter(
            phone_number=phone_number,
            code=code,
            is_verified=False,
            expires_at__gt=timezone.now()
        ).first()
        
        if token:
            # Mark as verified
            token.is_verified = True
            token.save()
            
            # Get or create user
            user, created = CustomUser.objects.get_or_create(
                phone_number=phone_number,
                defaults={'is_customer': True} # Default new logins to customer
            )
            
            # Log the user in
            auth_login(request, user)
            
            # Clear session
            if 'otp_phone_number' in request.session:
                del request.session['otp_phone_number']
                
            messages.success(request, _("Successfully logged in!"))
            return redirect('dashboard:home')
        else:
            messages.error(request, _("Invalid or expired code."))
            return redirect('otp:verify_otp')
            
    return render(request, 'otp/verify_otp.html', {'phone_number': phone_number})

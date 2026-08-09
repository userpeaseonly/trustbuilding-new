from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.utils.translation import gettext as _

from .forms import PhoneAuthenticationForm


def login_view(request):
    """Phone-based login view"""
    # Redirect if already authenticated
    if request.user.is_authenticated:
        return redirect('dashboard:home')
    
    if request.method == 'POST':
        form = PhoneAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            phone_number = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=phone_number, password=password)
            
            if user is not None:
                auth_login(request, user)
                messages.success(request, _('Welcome back, {}!').format(user.full_name or user.phone_number))

                next_page = request.GET.get('next', 'dashboard:home')
                return redirect(next_page)
            else:
                messages.error(request, _('Invalid phone number or password.'))
        else:
            messages.error(request, _('Please correct the errors below.'))
    else:
        form = PhoneAuthenticationForm()
    
    return render(request, 'users/login.html', {'form': form})


def logout_view(request):
    """Logout view"""
    auth_logout(request)
    messages.success(request, _('You have been logged out successfully.'))
    return redirect('users:login')



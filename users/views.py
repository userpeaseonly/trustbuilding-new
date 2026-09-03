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


from django.contrib.auth.decorators import login_required
from .models import CustomUser, StaffProfile
from .forms import StaffCreationForm, CustomerRegistrationForm
from django.db.models import Q

@login_required
def staff_list_view(request):
    """Company staff management view"""
    if not request.user.is_company:
        return redirect('dashboard:home')
        
    staff_profiles = StaffProfile.objects.filter(company=request.user).select_related('user')
    
    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data['phone_number']
            full_name = form.cleaned_data['full_name']
            position = form.cleaned_data.get('position', '')
            
            user, created = CustomUser.objects.get_or_create(
                phone_number=phone,
                defaults={
                    'full_name': full_name,
                    'is_staff_member': True
                }
            )
            if not created:
                user.is_staff_member = True
                user.full_name = full_name
                user.save(update_fields=['is_staff_member', 'full_name'])
                
            StaffProfile.objects.get_or_create(user=user, company=request.user, defaults={'position': position})
            messages.success(request, _("Staff member added successfully!"))
            return redirect('users:staff_list')
    else:
        form = StaffCreationForm()
        
    return render(request, 'users/staff_list.html', {
        'staff_profiles': staff_profiles,
        'form': form,
        'page_title': _("Manage Staff Members")
    })


@login_required
def customer_list_view(request):
    """Customer directory listing & customer registration"""
    query = request.GET.get('q', '').strip()
    customers = CustomUser.objects.filter(is_customer=True).order_by('-created_at')
    
    if query:
        customers = customers.filter(
            Q(phone_number__icontains=query) | Q(full_name__icontains=query) | Q(passport_jshshr__icontains=query)
        )
        
    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.is_customer = True
            customer.save()
            messages.success(request, _("Customer profile registered successfully!"))
            return redirect('users:customer_list')
    else:
        form = CustomerRegistrationForm()
        
    return render(request, 'users/customer_list.html', {
        'customers': customers,
        'form': form,
        'query': query,
        'page_title': _("Customer Directory")
    })




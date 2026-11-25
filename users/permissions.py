from urllib.parse import urlparse
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, resolve_url
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from functools import wraps

# All possible permissions mapping for UI rendering
AVAILABLE_PERMISSIONS = {
    'buildings': {
        'label': _('Buildings & Apartments'),
        'actions': [
            ('view_buildings', _('View')),
            ('create_buildings', _('Create')),
            ('edit_buildings', _('Edit')),
            ('delete_buildings', _('Delete')),
        ]
    },
    'customers': {
        'label': _('Customers'),
        'actions': [
            ('view_customers', _('View')),
            ('create_customers', _('Create')),
            ('edit_customers', _('Edit')),
            ('delete_customers', _('Delete')),
        ]
    },
    'contracts': {
        'label': _('Contracts'),
        'actions': [
            ('view_contracts', _('View')),
            ('create_contracts', _('Create')),
            ('edit_contracts', _('Edit')),
            ('delete_contracts', _('Delete')),
        ]
    },
    'payments': {
        'label': _('Payments'),
        'actions': [
            ('view_payments', _('View')),
            ('create_payments', _('Create')),
            ('edit_payments', _('Edit')),
            ('delete_payments', _('Delete')),
        ]
    },
    'reports': {
        'label': _('Reports & Analytics'),
        'actions': [
            ('view_reports', _('View Dashboard & Financials')),
        ]
    },
    'finance': {
        'label': _('Finance & Cash Desks'),
        'actions': [
            ('view_finance', _('View Cash Flow & Balances')),
            ('manage_finance', _('Record Incomes, Expenses & Transfers')),
        ]
    },
    'sms': {
        'label': _('SMS Marketing'),
        'actions': [
            ('view_sms', _('View Log & Cost')),
            ('send_sms', _('Send SMS')),
        ]
    },
    'staff': {
        'label': _('Staff & Roles'),
        'actions': [
            ('view_staff', _('View')),
            ('create_staff', _('Create')),
            ('edit_staff', _('Edit')),
            ('delete_staff', _('Delete')),
        ]
    },
}

def has_permission(user, permission_code):
    """
    Check if the user has a specific permission.
    - Company Admin has all permissions.
    - Staff Member has permissions defined in their assigned role.
    """
    if not user.is_authenticated:
        return False
        
    if user.is_company:
        return True
        
    if user.is_staff_member:
        try:
            profile = user.staff_profile
            if profile and profile.role:
                return permission_code in profile.role.permissions
        except Exception: # Catches RelatedObjectDoesNotExist
            return False
            
    return False

_SAFE_LANDING_ROUTES = [
    ('view_reports', 'dashboard:home'),
    ('view_contracts', 'contract:list'),
    ('create_payments', 'contract:quick_payment'),
    ('view_buildings', 'building:list'),
    ('view_customers', 'users:customer_list'),
    ('view_finance', 'finance:overview'),
    ('view_staff', 'users:staff_list'),
    ('view_sms', 'dashboard:sms_usage'),
]


def get_safe_redirect_for_user(user):
    """Return a URL name the user actually has access to, or None if none."""
    if not user.is_authenticated:
        return 'otp:request_otp'
    if getattr(user, 'is_customer', False) and not (user.is_company or getattr(user, 'is_staff_member', False)):
        return 'customer_portal:home'
    for perm, url_name in _SAFE_LANDING_ROUTES:
        if has_permission(user, perm):
            return url_name
    return None


def require_permission(permission_code):
    """
    Decorator for views that checks if the user has a specific permission.
    Prevents redirect loops when referrer or dashboard itself is inaccessible.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('otp:request_otp')
            if has_permission(request.user, permission_code):
                return view_func(request, *args, **kwargs)

            messages.error(request, _("You don't have permission to perform this action."))
            referer = request.META.get('HTTP_REFERER')
            if referer and url_has_allowed_host_and_scheme(
                referer,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                if urlparse(referer).path != request.path:
                    return redirect(referer)

            fallback = get_safe_redirect_for_user(request.user)
            if not fallback or resolve_url(fallback) == request.path:
                return HttpResponseForbidden("Permission denied.")
            return redirect(fallback)
        return _wrapped_view
    return decorator

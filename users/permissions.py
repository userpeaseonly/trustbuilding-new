from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
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

def require_permission(permission_code):
    """
    Decorator for views that checks if the user has a specific permission.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if has_permission(request.user, permission_code):
                return view_func(request, *args, **kwargs)
            else:
                messages.error(request, _("You don't have permission to perform this action."))
                # Referer redirect or dashboard
                referer = request.META.get('HTTP_REFERER')
                if referer:
                    return redirect(referer)
                return redirect('dashboard:home')
        return _wrapped_view
    return decorator

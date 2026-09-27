from django import template
from users.permissions import has_permission

register = template.Library()

@register.filter(name='has_perm')
def has_perm(user, permission_code):
    return has_permission(user, permission_code)

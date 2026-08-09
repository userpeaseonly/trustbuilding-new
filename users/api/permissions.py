from rest_framework.permissions import BasePermission


class IsStudent(BasePermission):
    """
    Grants access only to authenticated users who have a student profile.
    Used to restrict all mobile API endpoints to students exclusively.
    """

    message = 'Access restricted to student accounts only.'

    def has_permission(self, request, view):
        return (
            request.user is not None
            and request.user.is_authenticated
            and hasattr(request.user, 'student_profile')
        )

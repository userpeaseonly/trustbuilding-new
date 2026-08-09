from __future__ import annotations

import random
import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .permissions import IsStudent
from users.models import Branch

from .serializers import (
    AboutUsBranchSerializer,
    DirectReferralSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
    ProfileUpdateSerializer,
    PublicReferralSerializer,
    ReferredLeadSerializer,
    SetEnglishLevelSerializer,
    SetFaceImageSerializer,
    SetLocationSerializer,
    SetProfilePictureSerializer,
    SocialSerializer,
    TokenResponseSerializer,
    UserProfileSerializer,
)

User = get_user_model()

# Cache key helpers
_OTP_KEY = "pwd_reset_otp:{phone}"           # stores OTP code
_OTP_TTL = 60 * 10                            # 10 minutes
_RESET_TOKEN_KEY = "pwd_reset_token:{token}"  # stores phone after OTP verified
_RESET_TOKEN_TTL = 60 * 15                    # 15 minutes


class AboutUsView(APIView):
    """GET /api/v1/about-us/ — public branch information for the mobile app."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['About Us'],
        summary='List branches and branch locations',
        responses={200: OpenApiResponse(description='{"branches": [...]}')},
    )
    def get(self, request):
        branches = Branch.objects.order_by('name')
        return Response({
            'branches': AboutUsBranchSerializer(branches, many=True).data,
        })


def _make_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))


def _make_reset_token() -> str:
    return secrets.token_urlsafe(32)


class LoginView(APIView):
    """
    POST /api/v1/auth/login
    Authenticate with phone number and password.
    Returns JWT access + refresh tokens.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginSerializer,
        responses={200: TokenResponseSerializer, 400: OpenApiResponse(description='Invalid credentials')},
        tags=['Auth'],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout
    Blacklist the provided refresh token, invalidating the session.
    """

    permission_classes = [IsStudent]

    @extend_schema(
        request=LogoutSerializer,
        responses={204: None, 400: OpenApiResponse(description='Invalid or missing token')},
        tags=['Auth'],
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token = RefreshToken(serializer.validated_data['refresh'])
            token.blacklist()
        except TokenError:
            return Response({'detail': 'Token is invalid or already blacklisted.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """
    GET  /api/v1/auth/me  — return current user profile.
    PATCH /api/v1/auth/me  — update full_name, gender, profile_picture.
    """

    permission_classes = [IsStudent]

    @extend_schema(responses={200: UserProfileSerializer}, tags=['Auth'])
    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)

    @extend_schema(
        request=ProfileUpdateSerializer,
        responses={200: UserProfileSerializer},
        tags=['Auth'],
    )
    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserProfileSerializer(request.user).data)

class SetEnglishLevelView(APIView):
    """PATCH /api/v1/auth/me/english-level/ — set student english level."""

    permission_classes = [IsStudent]

    @extend_schema(
        request=SetEnglishLevelSerializer,
        responses={200: OpenApiResponse(description='{"english_level": "A1"}')},
        tags=['Auth'],
    )
    def patch(self, request):
        serializer = SetEnglishLevelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        student = getattr(request.user, 'student_profile', None)
        if not student:
            return Response({'detail': 'Student profile not found for this user.'}, status=status.HTTP_400_BAD_REQUEST)

        student.english_level = serializer.validated_data['english_level']
        student.save(update_fields=['english_level'])

        return Response({'english_level': student.english_level})



class SetLocationView(APIView):
    """GET/PATCH /api/v1/auth/me/location — get or set student location (latitude/longitude)."""

    permission_classes = [IsStudent]

    @extend_schema(
        responses={200: OpenApiResponse(description='{"latitude": float, "longitude": float}')},
        tags=['Auth'],
    )
    def get(self, request):
        student = request.user.student_profile
        return Response({
            'latitude': student.latitude,
            'longitude': student.longitude,
        })

    @extend_schema(
        request=SetLocationSerializer,
        responses={200: OpenApiResponse(description='{"latitude": float, "longitude": float}'), 400: OpenApiResponse(description='Student profile not found')},
        tags=['Auth'],
    )
    def patch(self, request):
        serializer = SetLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        student = getattr(request.user, 'student_profile', None)
        if not student:
            return Response({'detail': 'Student profile not found for this user.'}, status=status.HTTP_400_BAD_REQUEST)

        student.latitude = serializer.validated_data['latitude']
        student.longitude = serializer.validated_data['longitude']
        student.save(update_fields=['latitude', 'longitude'])

        return Response({
            'latitude': student.latitude,
            'longitude': student.longitude,
        }, status=status.HTTP_200_OK)


class SetProfilePictureView(APIView):
    """PATCH /api/v1/auth/me/profile-picture — set profile picture."""

    permission_classes = [IsStudent]

    @extend_schema(
        request=SetProfilePictureSerializer,
        responses={200: OpenApiResponse(description='{"detail": "Profile picture updated successfully."}')},
        tags=['Auth'],
    )
    def patch(self, request):
        serializer = SetProfilePictureSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Profile picture updated successfully.'}, status=status.HTTP_200_OK)


class SetFaceImageView(APIView):
    """PATCH /api/v1/auth/me/face-image — set face image."""

    permission_classes = [IsStudent]

    @extend_schema(
        request=SetFaceImageSerializer,
        responses={200: OpenApiResponse(description='{"detail": "Face image updated successfully."}')},
        tags=['Auth'],
    )
    def patch(self, request):
        serializer = SetFaceImageSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Face image updated successfully.'}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Password reset — 3-step OTP flow
# ---------------------------------------------------------------------------

class PasswordResetRequestView(APIView):
    """
    POST /api/v1/auth/password-reset/
    Step 1 — send a 6-digit OTP to the user's registered phone number.
    OTP is valid for 10 minutes. Repeated calls replace the previous OTP.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={200: OpenApiResponse(description='OTP sent successfully')},
        tags=['Auth'],
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']

        # Verify the user has a linked Telegram account before generating OTP
        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            # Already validated in serializer — shouldn't reach here
            return Response({'detail': 'OTP sent to your Telegram.'}, status=status.HTTP_200_OK)

        if not user.telegram_chat_id:
            return Response(
                {'detail': 'Your account is not linked to Telegram yet. '
                            'Open the Imaan bot and share your contact to link it first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp = _make_otp()
        cache.set(_OTP_KEY.format(phone=phone_number), otp, _OTP_TTL)

        # Send OTP via Telegram bot
        from telegram_bot.utils import send_otp
        sent = send_otp(user.telegram_chat_id, otp)
        if not sent:
            import logging as _logging
            _logging.getLogger(__name__).error("Failed to send OTP to chat_id %s", user.telegram_chat_id)

        # Always return success to avoid user enumeration via timing
        return Response({'detail': 'OTP sent to your Telegram.'}, status=status.HTTP_200_OK)


class PasswordResetVerifyView(APIView):
    """
    POST /api/v1/auth/password-reset/verify/
    Step 2 — verify the OTP.
    Returns a short-lived reset_token (15 min) to be used in step 3.
    The OTP is consumed (deleted) on first successful use.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=PasswordResetVerifySerializer,
        responses={
            200: OpenApiResponse(description='OTP verified — reset_token returned'),
            400: OpenApiResponse(description='Invalid or expired OTP'),
        },
        tags=['Auth'],
    )
    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number'].strip()
        otp_submitted = serializer.validated_data['otp'].strip()

        cached_otp = cache.get(_OTP_KEY.format(phone=phone_number))

        if not cached_otp or cached_otp != otp_submitted:
            return Response({'detail': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)

        # Consume the OTP immediately so it can't be reused
        cache.delete(_OTP_KEY.format(phone=phone_number))

        # Issue a short-lived reset token bound to this phone number
        reset_token = _make_reset_token()
        cache.set(_RESET_TOKEN_KEY.format(token=reset_token), phone_number, _RESET_TOKEN_TTL)

        return Response({'reset_token': reset_token}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """
    POST /api/v1/auth/password-reset/confirm/
    Step 3 — set a new password using the reset_token from step 2.
    The token is consumed after a successful reset.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={
            200: OpenApiResponse(description='Password changed successfully'),
            400: OpenApiResponse(description='Invalid token or password validation failed'),
        },
        tags=['Auth'],
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reset_token = serializer.validated_data['reset_token']
        new_password = serializer.validated_data['new_password']

        phone_number = cache.get(_RESET_TOKEN_KEY.format(token=reset_token))
        if not phone_number:
            return Response({'detail': 'Reset token is invalid or has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return Response({'detail': 'Reset token is invalid or has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        # Run Django's password validators
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as e:
            return Response({'detail': list(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])

        # Consume the reset token so it can't be reused
        cache.delete(_RESET_TOKEN_KEY.format(token=reset_token))

        return Response({'detail': 'Password changed successfully.'}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Referral system
# ---------------------------------------------------------------------------

class MyReferralsView(APIView):
    """
    GET  /api/v1/auth/me/referrals/  — list all leads referred by this student.
    POST /api/v1/auth/me/referrals/  — submit a new referral (Method 1).
    """

    permission_classes = [IsStudent]

    @extend_schema(
        responses={200: ReferredLeadSerializer(many=True)},
        tags=['Referrals'],
    )
    def get(self, request):
        student = getattr(request.user, 'student_profile', None)
        if not student:
            return Response({'detail': 'Student profile not found.'}, status=status.HTTP_400_BAD_REQUEST)

        leads = student.referred_leads.all().order_by('-created_at')
        return Response(ReferredLeadSerializer(leads, many=True).data)

    @extend_schema(
        request=DirectReferralSerializer,
        responses={
            201: ReferredLeadSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
        tags=['Referrals'],
    )
    def post(self, request):
        student = getattr(request.user, 'student_profile', None)
        if not student:
            return Response({'detail': 'Student profile not found.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = DirectReferralSerializer(data=request.data, context={'student': student})
        serializer.is_valid(raise_exception=True)
        lead = serializer.save()
        return Response(ReferredLeadSerializer(lead).data, status=status.HTTP_201_CREATED)


class PublicReferralSubmitView(APIView):
    """
    POST /api/v1/referrals/submit/
    Public endpoint — external landing page submits a referral form (Method 2).
    Body: full_name, phone_number, age, city, referral_code
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=PublicReferralSerializer,
        responses={
            201: OpenApiResponse(description='Referral submitted successfully'),
            400: OpenApiResponse(description='Validation error'),
        },
        tags=['Referrals'],
    )
    def post(self, request):
        serializer = PublicReferralSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = serializer.save()
        return Response(
            {'detail': 'Thank you! Your information has been submitted.', 'id': lead.id},
            status=status.HTTP_201_CREATED,
        )


class MyReferralUrlView(APIView):
    """
    GET /api/v1/auth/me/referral-url/
    Returns the personalised referral URL for the authenticated student.
    URL format: <BASE_REFERRAL_URL>?refercode=<uuid>
    """

    permission_classes = [IsStudent]

    @extend_schema(
        responses={
            200: OpenApiResponse(description='{"url": "https://example.com/?refercode=<uuid>"}'),
            400: OpenApiResponse(description='Student profile not found or BASE_REFERRAL_URL not configured'),
        },
        tags=['Referrals'],
    )
    def get(self, request):
        from django.conf import settings as django_settings

        student = getattr(request.user, 'student_profile', None)
        if not student:
            return Response(
                {'detail': 'Student profile not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        base_url = getattr(django_settings, 'BASE_REFERRAL_URL', '').rstrip('/')
        if not base_url:
            return Response(
                {'detail': 'Referral URL is not configured.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        url = f"{base_url}?refercode={student.referral_code}"
        return Response({'url': url})


class MyCourseProgressView(APIView):
    """
    GET /api/v1/auth/me/course-progress/
    Returns the student's current course level and progress counters.
    """

    permission_classes = [IsStudent]

    @extend_schema(
        responses={200: OpenApiResponse(description='{"course_name": "...", "current_level": "...", "level_progress": {"done": int, "total": int, "percent": int}}')},
        tags=['Auth'],
    )
    def get(self, request):
        from django.utils import timezone
        from groups.views.group import _count_finished_lessons
        from users.api.serializers import UserProfileSerializer

        student = request.user.student_profile
        group = student.group

        if not group or not group.course:
            return Response({
                'course_name': None,
                'current_level': None,
                'level_progress': {'done': 0, 'total': 0, 'percent': 0},
            })

        course = group.course
        done = _count_finished_lessons(group, timezone.localdate())
        total = course.total_lessons or 0

        # Reuse the same lesson-name resolution logic from UserProfileSerializer
        serializer_instance = UserProfileSerializer(context={'request': request})
        current_level = serializer_instance._get_current_or_upcoming_lesson_name(group)

        return Response({
            'course_name': course.name,
            'current_level': current_level,
            'level_progress': {
                'done': done,
                'total': total,
                'percent': int(round((done / total) * 100)) if total else 0,
            },
            'day_type': {
                'value': group.day_type,
                'label': group.get_day_type_display(),
            },
        })


class MySocialView(APIView):
    """
    GET /PATCH /api/v1/auth/me/social/
    Get or update Instagram/Telegram usernames and telegram_linked status.
    """

    permission_classes = [IsStudent]

    @extend_schema(
        responses={200: OpenApiResponse(description='{"instagram": str, "telegram": str, "telegram_linked": bool}')},
        tags=['Auth'],
    )
    def get(self, request):
        user = request.user
        return Response({
            'instagram': user.instagram_username,
            'telegram': user.telegram_username,
            'telegram_linked': bool(user.telegram_chat_id),
        })

    @extend_schema(
        request=SocialSerializer,
        responses={200: OpenApiResponse(description='{"instagram": str, "telegram": str, "telegram_linked": bool}')},
        tags=['Auth'],
    )
    def patch(self, request):
        serializer = SocialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if 'instagram' in serializer.validated_data:
            user.instagram_username = serializer.validated_data['instagram']
        if 'telegram' in serializer.validated_data:
            user.telegram_username = serializer.validated_data['telegram']
        user.save(update_fields=['instagram_username', 'telegram_username'])
        return Response({
            'instagram': user.instagram_username,
            'telegram': user.telegram_username,
            'telegram_linked': bool(user.telegram_chat_id),
        })


class MyTeachersView(APIView):
    """
    GET /api/v1/auth/me/teachers/
    Returns the teacher and support_teacher of the student's current group.
    """

    permission_classes = [IsStudent]

    @extend_schema(
        responses={200: OpenApiResponse(description='{"teacher": {...}, "support_teacher": {...}}')},
        tags=['Auth'],
    )
    def get(self, request):
        student = getattr(request.user, 'student_profile', None)
        group = student.group if student else None

        def teacher_info(user):
            if not user:
                return {
                    'id': None, 'full_name': None, 'phone_number': None,
                    'profile_picture': None, 'language_level': None, 'specialization': None,
                }
            employee = getattr(user, 'employee', None)
            pic = None
            if user.profile_picture:
                pic = request.build_absolute_uri(user.profile_picture.url)
            return {
                'id': user.id,
                'full_name': user.full_name,
                'phone_number': str(user.phone_number) if user.phone_number else None,
                'profile_picture': pic,
                'language_level': employee.language_level if employee else '',
                'specialization': employee.specialization if employee else '',
            }

        return Response({
            'teacher': teacher_info(group.teacher if group else None),
            'support_teacher': teacher_info(group.support_teacher if group else None),
        })

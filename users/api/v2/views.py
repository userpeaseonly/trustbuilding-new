from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import OpenApiResponse

from .serializers import MeV2Serializer, ReferredLeadV2Serializer
from users.api.permissions import IsStudent


class MeV2View(APIView):
    """
    GET /api/v2/auth/me/
    Returns a focused student profile for the mobile app.
    Non-student users receive 403.
    """

    permission_classes = [IsStudent]

    @extend_schema(
        responses={
            200: MeV2Serializer,
            403: None,
        },
        tags=['Me v2'],
        summary='Get current student profile (v2)',
    )
    def get(self, request):
        user = request.user
        student = getattr(user, 'student_profile', None)
        if not student:
            return Response(
                {'detail': 'This endpoint is only available to students.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = MeV2Serializer(user, context={'request': request})
        return Response(serializer.data)


class MyReferralsV2View(APIView):
    """
    GET /api/v2/auth/me/referrals/
    Returns all leads referred by the authenticated student, with richer details:
    - referral_step + display label
    - lead block (id, status, pipeline_stage, created_at)
    - student block if the lead has converted (enrollment, group, payment_status,
      student status, attendance count)
    """

    permission_classes = [IsStudent]

    @extend_schema(
        responses={
            200: ReferredLeadV2Serializer(many=True),
            400: OpenApiResponse(description='Student profile not found'),
        },
        tags=['Referrals v2'],
        summary='List referred leads/students with step tracking (v2)',
    )
    def get(self, request):
        student = getattr(request.user, 'student_profile', None)
        if not student:
            return Response(
                {'detail': 'Student profile not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        leads = (
            student.referred_leads
            .select_related('pipeline_stage')
            .order_by('-created_at')
        )
        return Response(ReferredLeadV2Serializer(leads, many=True).data)

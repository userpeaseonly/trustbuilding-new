from __future__ import annotations

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes


class MeV2Serializer(serializers.Serializer):
    """Read-only serializer for GET /api/v2/auth/me/"""

    id = serializers.IntegerField()
    name = serializers.CharField()
    phone_number = serializers.CharField()
    date_of_birth = serializers.DateField(allow_null=True)
    group_name = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()
    profile_completion_percentage = serializers.SerializerMethodField()
    enrollment_date = serializers.DateField(allow_null=True)
    profile_picture = serializers.CharField(allow_null=True, read_only=True)
    face_image = serializers.CharField(allow_null=True, read_only=True)

    # ── Profile completion ──────────────────────────────────────────────────
    # Fields counted: profile_picture, full_name, phone_number, date_of_birth,
    #                 father_name, father_phone, mother_name, school_name  (8 total)
    _PROFILE_FIELDS_TOTAL = 8

    @extend_schema_field(OpenApiTypes.STR)
    def get_group_name(self, obj) -> str | None:
        student = getattr(obj, 'student_profile', None)
        if student and student.group:
            return student.group.name
        return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_branch_name(self, obj) -> str | None:
        student = getattr(obj, 'student_profile', None)
        if student and student.branch:
            return student.branch.name
        return None

    @extend_schema_field(OpenApiTypes.INT)
    def get_profile_completion_percentage(self, obj) -> int:
        student = getattr(obj, 'student_profile', None)
        filled = 0

        # User-level fields
        if obj.full_name and obj.full_name.strip():
            filled += 1
        if obj.phone_number:
            filled += 1
        if obj.profile_picture:
            filled += 1

        # Student-level fields
        if student:
            if student.date_of_birth:
                filled += 1
            if student.father_name and student.father_name.strip():
                filled += 1
            if student.father_phone and student.father_phone.strip():
                filled += 1
            if student.mother_name and student.mother_name.strip():
                filled += 1
            if student.school_name and student.school_name.strip():
                filled += 1

        return round((filled / self._PROFILE_FIELDS_TOTAL) * 100)

    def _absolute_url(self, image_field) -> str | None:
        if not image_field:
            return None
        request = self.context.get('request')
        url = image_field.url
        return request.build_absolute_uri(url) if request else url

    def to_representation(self, obj):
        student = getattr(obj, 'student_profile', None)
        return {
            'id': obj.id,
            'name': obj.full_name,
            'phone_number': str(obj.phone_number) if obj.phone_number else None,
            'date_of_birth': student.date_of_birth if student else None,
            'group_name': self.get_group_name(obj),
            'branch_name': self.get_branch_name(obj),
            'profile_completion_percentage': self.get_profile_completion_percentage(obj),
            'enrollment_date': student.enrollment_date if student else None,
            'profile_picture': self._absolute_url(obj.profile_picture),
            'face_image': self._absolute_url(obj.face_image),
        }


# ---------------------------------------------------------------------------
# Referral v2 serializers
# ---------------------------------------------------------------------------

class ReferredLeadStudentSerializer(serializers.Serializer):
    """Student info included once a referred lead converts."""
    id = serializers.IntegerField()
    enrollment_date = serializers.DateField()
    group = serializers.SerializerMethodField()
    payment_status = serializers.CharField()
    status = serializers.CharField()
    attendance_count = serializers.SerializerMethodField()

    @extend_schema_field(OpenApiTypes.STR)
    def get_group(self, obj) -> str | None:
        return obj.group.name if obj.group else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_attendance_count(self, obj) -> int:
        return obj.attendances.filter(status__in=('present', 'late')).count()


class ReferredLeadV2Serializer(serializers.Serializer):
    """
    Rich representation of a referred lead/student for v2 API.

    'lead' block is always present (leads are never hard-deleted).
    'student' block is present only after the lead converts to a student.
    """
    id = serializers.IntegerField(help_text="Lead ID")
    full_name = serializers.CharField()
    phone_number = serializers.SerializerMethodField()
    referral_step = serializers.CharField()
    referral_step_display = serializers.SerializerMethodField()
    lead = serializers.SerializerMethodField()
    student = serializers.SerializerMethodField()

    @extend_schema_field(OpenApiTypes.STR)
    def get_phone_number(self, obj) -> str | None:
        return str(obj.phone_number) if obj.phone_number else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_referral_step_display(self, obj) -> str:
        return obj.get_referral_step_display()

    @extend_schema_field({
        'type': 'object',
        'properties': {
            'id': {'type': 'integer'},
            'status': {'type': 'string'},
            'pipeline_stage': {'type': 'string', 'nullable': True},
            'created_at': {'type': 'string', 'format': 'date-time'},
        },
    })
    def get_lead(self, obj) -> dict:
        return {
            'id': obj.id,
            'status': obj.status,
            'pipeline_stage': obj.pipeline_stage.name if obj.pipeline_stage else None,
            'created_at': obj.created_at,
        }

    @extend_schema_field({
        'type': 'object',
        'nullable': True,
        'properties': {
            'id': {'type': 'integer'},
            'enrollment_date': {'type': 'string', 'format': 'date'},
            'group': {'type': 'string', 'nullable': True},
            'payment_status': {'type': 'string'},
            'status': {'type': 'string'},
            'attendance_count': {'type': 'integer'},
        },
    })
    def get_student(self, obj) -> dict | None:
        """
        Find the student that was created from this lead.
        Uses phone number match since there is no direct FK from lead→student.
        """
        from students.models import Student
        if not obj.phone_number:
            return None
        try:
            student = Student.objects.select_related('group').get(
                user__phone_number=obj.phone_number
            )
        except Student.DoesNotExist:
            return None
        return ReferredLeadStudentSerializer(student).data

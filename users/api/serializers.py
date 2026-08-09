from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from students.models import GroupTransfer
from users.models import Branch

User = get_user_model()


class AboutUsBranchSerializer(serializers.ModelSerializer):
    location = serializers.CharField(source='address', read_only=True)
    lat = serializers.DecimalField(source='latitude', max_digits=9, decimal_places=6, allow_null=True, read_only=True)
    lng = serializers.DecimalField(source='longitude', max_digits=9, decimal_places=6, allow_null=True, read_only=True)

    class Meta:
        model = Branch
        fields = [
            'id',
            'name',
            'short_name',
            'location',
            'latitude',
            'longitude',
            'lat',
            'lng',
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    """User data returned in auth responses and /me endpoint."""

    progress = serializers.SerializerMethodField()
    branch = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()
    face_id = serializers.SerializerMethodField()
    date_added_to_group = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    school_name = serializers.SerializerMethodField()
    telegram_linked = serializers.SerializerMethodField()
    instagram = serializers.CharField(source='instagram_username', read_only=True)
    telegram = serializers.CharField(source='telegram_username', read_only=True)
    referral_code = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = [
            'id',
            'phone_number',
            'full_name',
            'gender',
            'profile_picture',
            'face_image',
            'face_id',
            'instagram',
            'telegram',
            'telegram_linked',
            'is_student',
            'is_teacher',
            'progress',
            'branch',
            'group',
            'date_added_to_group',
            'location',
            'school_name',
            'referral_code',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'phone_number',
            'is_student',
            'is_teacher',
            'status',
            'created_at',
            'updated_at',
            'face_id',
            'progress',
            'branch',
            'group',
            'date_added_to_group',
            'location',
            'school_name',
            'telegram_linked',
            'referral_code',
        ]

    def _get_student_profile(self, obj):
        return getattr(obj, 'student_profile', None)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_referral_code(self, obj):
        student = self._get_student_profile(obj)
        if not student:
            return None
        return str(student.referral_code)

    def _teacher_info(self, user):
        if not user:
            return {'id': None, 'full_name': None, 'phone_number': None, 'profile_picture': None, 'language_level': None, 'specialization': None}
        employee = getattr(user, 'employee', None)
        request = self.context.get('request')
        profile_picture = None
        if user.profile_picture:
            profile_picture = request.build_absolute_uri(user.profile_picture.url) if request else user.profile_picture.url
        return {
            'id': user.id,
            'full_name': user.full_name,
            'phone_number': str(user.phone_number) if user.phone_number else None,
            'profile_picture': profile_picture,
            'language_level': employee.language_level if employee else '',
            'specialization': employee.specialization if employee else '',
        }

    @extend_schema_field(serializers.BooleanField())
    def get_face_id(self, obj):
        return bool(obj.face_image)

    @extend_schema_field(serializers.BooleanField())
    def get_telegram_linked(self, obj):
        return bool(obj.telegram_chat_id)

    @extend_schema_field(serializers.DictField())
    def get_branch(self, obj):
        student = self._get_student_profile(obj)
        if not student or not student.branch:
            return None
        return {
            'id': student.branch_id,
            'name': student.branch.name,
        }

    @extend_schema_field(serializers.DictField())
    def get_group(self, obj):
        student = self._get_student_profile(obj)
        if not student or not student.group:
            return None

        group = student.group
        course = group.course

        # Keep LP exactly consistent with groups list calculation.
        from groups.views.group import _count_finished_lessons
        done = _count_finished_lessons(group, timezone.localdate())
        total = course.total_lessons if course else 0

        # Use the same current/upcoming lesson calendar logic as dashboard schedule.
        current_level = self._get_current_or_upcoming_lesson_name(group)

        return {
            'id': group.id,
            'name': group.name,
            'course_name': course.name if course else None,
            'day_type': {
                'value': group.day_type,
                'label': group.get_day_type_display(),
            },
            'teacher': self._teacher_info(group.teacher),
            'support_teacher': self._teacher_info(group.support_teacher),
            'current_level': current_level,
            'level_progress': {
                'done': done,
                'total': total,
                'percent': int(round((done / total) * 100)) if total else 0,
            },
        }

    @extend_schema_field(serializers.DateField())
    def get_date_added_to_group(self, obj):
        student = self._get_student_profile(obj)
        if not student or not student.group:
            return None

        transfer = (
            GroupTransfer.objects
            .filter(student=student, to_group=student.group)
            .order_by('-transfer_date', '-transferred_at')
            .first()
        )
        if transfer and transfer.transfer_date:
            return transfer.transfer_date
        return student.enrollment_date

    @extend_schema_field(serializers.DictField())
    def get_location(self, obj):
        student = self._get_student_profile(obj)
        if not student:
            return None
        if student.latitude is None or student.longitude is None:
            return None
        return {
            'latitude': student.latitude,
            'longitude': student.longitude,
        }

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_school_name(self, obj):
        student = self._get_student_profile(obj)
        if not student:
            return None
        return student.school_name or ''

    def _get_current_or_upcoming_lesson_name(self, group):
        """Return today's lesson name or the next upcoming lesson name."""
        from datetime import timedelta
        from attendance.models import Holiday
        from courses.models import Lesson as CourseLesson
        from groups.models import GroupCourseHistory

        if not group.course:
            return None

        lessons = list(
            CourseLesson.objects
            .filter(module__course=group.course)
            .order_by('order')
            .values_list('title', flat=True)
        )
        if not lessons:
            return None

        today_date = timezone.localdate()
        day_map = {
            'odd': {0, 2, 4},
            'even': {1, 3, 5},
            'daily': {0, 1, 2, 3, 4, 5},
        }
        weekdays = day_map.get(group.day_type, {0, 2, 4})

        segment_start = group.start_date
        history_entry = (
            GroupCourseHistory.objects
            .filter(group=group, course=group.course)
            .order_by('-order')
            .first()
        )
        if history_entry and history_entry.started_on:
            segment_start = history_entry.started_on

        if not segment_start:
            return lessons[0]
        if segment_start > today_date:
            return lessons[0]

        holiday_dates = set(
            Holiday.objects
            .filter(date__gte=segment_start)
            .filter(date__lte=today_date + timedelta(days=3650))
            .filter(branch=group.branch)
            .values_list('date', flat=True)
        )
        holiday_dates |= set(
            Holiday.objects
            .filter(date__gte=segment_start)
            .filter(date__lte=today_date + timedelta(days=3650))
            .filter(branch__isnull=True)
            .values_list('date', flat=True)
        )

        current = segment_start
        lesson_idx = 0
        total = group.course.total_lessons if group.course else len(lessons)
        cap = min(total, len(lessons))

        while lesson_idx < cap:
            if current.weekday() in weekdays and current not in holiday_dates:
                if current >= today_date:
                    return lessons[lesson_idx]
                lesson_idx += 1
            current += timedelta(days=1)
            if (current - segment_start).days > 5475:
                break

        return lessons[-1] if lessons else None

    @extend_schema_field(serializers.IntegerField())
    def get_progress(self, obj):
        student = self._get_student_profile(obj)
        checks = [
            bool(obj.full_name),
            bool(obj.gender),
            bool(obj.profile_picture),
            bool(obj.face_image),
            bool(obj.instagram_username),
            bool(obj.telegram_username),
            bool(student and student.branch_id),
            bool(student and student.group_id),
            bool(student and student.enrollment_date),
            bool(student and student.school_name),
            bool(student and student.latitude is not None and student.longitude is not None),
        ]
        filled = sum(1 for c in checks if c)
        return int(round((filled / len(checks)) * 100))


class LoginSerializer(serializers.Serializer):
    """Validate phone_number + password and return the user instance."""

    phone_number = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        phone_number = attrs.get('phone_number', '').strip()
        password = attrs.get('password', '')

        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            raise serializers.ValidationError('Invalid phone number or password.')

        if not user.check_password(password):
            raise serializers.ValidationError('Invalid phone number or password.')

        if not user.is_active:
            raise serializers.ValidationError('This account is inactive.')

        attrs['user'] = user
        return attrs


class TokenResponseSerializer(serializers.Serializer):
    """Shape of the response returned on successful login (for Swagger docs)."""

    access = serializers.CharField()
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    """Refresh token to blacklist on logout."""

    refresh = serializers.CharField()


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Allowed fields a user can update on their own profile."""

    class Meta:
        model = User
        fields = ['full_name', 'gender', 'profile_picture', 'face_image', 'instagram_username', 'telegram_username']

class SetEnglishLevelSerializer(serializers.Serializer):
    """Set student English Level."""
    english_level = serializers.ChoiceField(choices=['A1', 'A2', 'B1', 'B2', 'C1', 'C2'])



class SetLocationSerializer(serializers.Serializer):
    """Set student GPS location from mobile app."""

    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)

    def validate_latitude(self, value):
        if value < -90 or value > 90:
            raise serializers.ValidationError('Latitude must be between -90 and 90.')
        return value

    def validate_longitude(self, value):
        if value < -180 or value > 180:
            raise serializers.ValidationError('Longitude must be between -180 and 180.')
        return value


class SocialSerializer(serializers.Serializer):
    """Update student's Instagram and Telegram usernames."""

    instagram = serializers.CharField(max_length=255, allow_blank=True, required=False)
    telegram = serializers.CharField(max_length=255, allow_blank=True, required=False)


class SetProfilePictureSerializer(serializers.ModelSerializer):
    """Set user's profile picture only."""

    class Meta:
        model = User
        fields = ['profile_picture']


class SetFaceImageSerializer(serializers.ModelSerializer):
    """Set user's face image only (used for face ID)."""

    class Meta:
        model = User
        fields = ['face_image']


# ---------------------------------------------------------------------------
# Password reset — OTP flow
# ---------------------------------------------------------------------------

class PasswordResetRequestSerializer(serializers.Serializer):
    """Step 1 — request an OTP for the given phone number."""

    phone_number = serializers.CharField()

    def validate_phone_number(self, value):
        value = value.strip()
        if not User.objects.filter(phone_number=value).exists():
            # Return generic message to avoid user enumeration
            raise serializers.ValidationError('No account found with this phone number.')
        return value


class PasswordResetVerifySerializer(serializers.Serializer):
    """Step 2 — verify the OTP; returns a short-lived reset token."""

    phone_number = serializers.CharField()
    otp = serializers.CharField(min_length=4, max_length=8)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Step 3 — set a new password using the reset token from step 2."""

    reset_token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)
    new_password_confirm = serializers.CharField(min_length=8, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': "Passwords do not match."})
        return attrs


# ---------------------------------------------------------------------------
# Referral serializers
# ---------------------------------------------------------------------------

def _phone_is_taken(phone_number: str) -> bool:
    """Return True if the phone number already exists in leads or students."""
    from leads.models import Lead
    from students.models import Student
    from phonenumber_field.phonenumber import PhoneNumber as PN
    import phonenumbers

    # Normalise to E.164 for comparison
    try:
        parsed = PN.from_string(phone_number)
        e164 = str(parsed) if parsed and parsed.is_valid() else phone_number
    except (phonenumbers.NumberParseException, Exception):
        e164 = phone_number

    if Lead.objects.filter(phone_number=e164).exists():
        return True
    if Student.objects.filter(user__phone_number=e164).exists():
        return True
    return False


class ReferredLeadSerializer(serializers.Serializer):
    """Read-only representation of a lead referred by a student."""
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    phone_number = serializers.SerializerMethodField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()

    def get_phone_number(self, obj) -> str | None:
        return str(obj.phone_number) if obj.phone_number else None


class DirectReferralSerializer(serializers.Serializer):
    """Method 1 — authenticated student submits full_name + phone_number."""
    full_name = serializers.CharField(max_length=255)
    phone_number = serializers.CharField(max_length=30)

    def validate_phone_number(self, value):
        from phonenumber_field.phonenumber import PhoneNumber as PN
        import phonenumbers
        try:
            parsed = PN.from_string(value)
        except (phonenumbers.NumberParseException, Exception):
            parsed = None
        if not parsed or not parsed.is_valid():
            raise serializers.ValidationError("Enter a valid phone number (e.g. +998901234567).")
        normalized = str(parsed)
        if _phone_is_taken(normalized):
            raise serializers.ValidationError("This phone number is already registered in the system.")
        return normalized

    def create(self, validated_data):
        from leads.models import Lead
        student = self.context['student']
        return Lead.objects.create(
            full_name=validated_data['full_name'],
            phone_number=validated_data['phone_number'],
            source='referral',
            branch=student.branch,
            referred_by_student=student,
        )


class PublicReferralSerializer(serializers.Serializer):
    """Method 2 — public form submission with referral_code."""
    full_name = serializers.CharField(max_length=255)
    phone_number = serializers.CharField(max_length=30)
    age = serializers.IntegerField(min_value=1, max_value=120)
    city = serializers.CharField(max_length=100)
    referral_code = serializers.UUIDField()

    def validate_phone_number(self, value):
        from phonenumber_field.phonenumber import PhoneNumber as PN
        import phonenumbers
        try:
            parsed = PN.from_string(value)
        except (phonenumbers.NumberParseException, Exception):
            parsed = None
        if not parsed or not parsed.is_valid():
            raise serializers.ValidationError("Enter a valid phone number (e.g. +998901234567).")
        normalized = str(parsed)
        if _phone_is_taken(normalized):
            raise serializers.ValidationError("This phone number is already registered in the system.")
        return normalized

    def validate_referral_code(self, value):
        from students.models import Student
        try:
            self._referring_student = Student.objects.select_related('branch').get(referral_code=value)
        except Student.DoesNotExist:
            raise serializers.ValidationError("Invalid referral code.")
        return value

    def create(self, validated_data):
        from leads.models import Lead
        student = self._referring_student
        notes = f"Age: {validated_data['age']}, City: {validated_data['city']}"
        return Lead.objects.create(
            full_name=validated_data['full_name'],
            phone_number=validated_data['phone_number'],
            source='referral',
            branch=student.branch,
            referred_by_student=student,
            notes=notes,
        )

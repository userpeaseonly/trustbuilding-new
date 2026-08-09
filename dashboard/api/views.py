from datetime import date, timedelta

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from groups.views.group import _count_finished_lessons
from users.api.permissions import IsStudent

from .serializers import HomeDashboardSerializer


def _calendar_week_since(start_date: date) -> int:
    """Return the calendar week number since group start_date (1-indexed)."""
    if not start_date:
        return 1
    today = timezone.localdate()
    if today < start_date:
        return 1
    delta_days = (today - start_date).days
    return (delta_days // 7) + 1


def _avatar_url(user, request) -> str | None:
    """Return the best available avatar URL: face_image → profile_picture → None."""
    image = user.face_image or user.profile_picture
    if not image:
        return None
    try:
        return request.build_absolute_uri(image.url)
    except Exception:
        return None


def _current_unit(group) -> str | None:
    """Return the title of the current/next upcoming lesson in the group's course."""
    from users.api.serializers import UserProfileSerializer
    serializer = UserProfileSerializer()
    return serializer._get_current_or_upcoming_lesson_name(group)


def _upcoming_homework(group) -> dict:
    """Return a stub based on the current/next lesson title. No due_date tracking yet."""
    null_homework = {
        "id": None,
        "title": None,
        "type": None,
        "due_date": None,
        "is_completed": False,
    }

    if not group or not group.course:
        return null_homework

    from courses.models import Lesson
    from users.api.serializers import UserProfileSerializer

    serializer = UserProfileSerializer()
    lesson_title = serializer._get_current_or_upcoming_lesson_name(group)
    if not lesson_title:
        return null_homework

    # Fetch the matching lesson record to get its id
    lesson = (
        Lesson.objects
        .filter(module__course=group.course, title=lesson_title)
        .order_by('order')
        .first()
    )

    return {
        "id": lesson.pk if lesson else None,
        "title": lesson_title,
        "type": None,       # will be filled in a future iteration
        "due_date": None,   # no due_date model yet
        "is_completed": False,
    }


class HomeDashboardView(APIView):
    """
    GET /api/v1/dashboard/home/

    Returns the student home-screen dashboard payload.

    Sections:
    - user_summary      : name, avatar, group name
    - academic_progress : english level, current lesson (unit), calendar week, lesson progress
    - gamification      : coin balance, leaderboard rank (static placeholder), movement
    - upcoming_homework : next lesson title (due_date & completion tracking not yet implemented)
    """

    permission_classes = [IsStudent]

    @extend_schema(
        tags=["Dashboard"],
        summary="Student home dashboard",
        responses={200: HomeDashboardSerializer},
    )
    def get(self, request):
        user = request.user
        student = getattr(user, "student_profile", None)

        if not student:
            return Response({"detail": "Student profile not found."}, status=400)

        group = student.group  # may be None
        course = group.course if group else None

        # ── user_summary ──────────────────────────────────────────────────────
        user_summary = {
            "first_name": user.full_name,
            "avatar_url": _avatar_url(user, request),
            "group_name": group.name if group else None,
        }

        # ── academic_progress ─────────────────────────────────────────────────
        done = _count_finished_lessons(group) if group else 0
        total = course.total_lessons if course else 0
        percent = int(round((done / total) * 100)) if total else 0

        academic_progress = {
            "current_level": course.name if course else None,
            "current_unit": _current_unit(group) if group else None,
            "current_week": _calendar_week_since(group.start_date) if group else None,
            "level_progress": {
                "done": done,
                "total": total,
                "percent": percent,
            },
        }

        # ── gamification ──────────────────────────────────────────────────────
        # Leaderboard rank and movement are static placeholders.
        # Real leaderboard (per-branch ranking with snapshot history) will be
        # implemented in a future iteration.
        gamification = {
            "coin_balance": student.coins,
            "leaderboard_rank": 0,
            "leaderboard_movement": "same",
        }

        # ── upcoming_homework ─────────────────────────────────────────────────
        upcoming_homework = _upcoming_homework(group)

        data = {
            "user_summary": user_summary,
            "academic_progress": academic_progress,
            "gamification": gamification,
            "upcoming_homework": upcoming_homework,
        }

        serializer = HomeDashboardSerializer(data)
        return Response(serializer.data)

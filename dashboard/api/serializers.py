from rest_framework import serializers


class UserSummarySerializer(serializers.Serializer):
    first_name = serializers.CharField()
    avatar_url = serializers.CharField(allow_null=True)
    group_name = serializers.CharField(allow_null=True)


class LevelProgressSerializer(serializers.Serializer):
    done = serializers.IntegerField()
    total = serializers.IntegerField()
    percent = serializers.IntegerField()


class AcademicProgressSerializer(serializers.Serializer):
    current_level = serializers.CharField(allow_null=True)
    current_unit = serializers.CharField(allow_null=True)
    current_week = serializers.IntegerField(allow_null=True)
    level_progress = LevelProgressSerializer()


class GamificationSerializer(serializers.Serializer):
    coin_balance = serializers.IntegerField()
    leaderboard_rank = serializers.IntegerField()
    leaderboard_movement = serializers.ChoiceField(choices=["up", "down", "same"])


class UpcomingHomeworkSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    title = serializers.CharField(allow_null=True)
    type = serializers.CharField(allow_null=True)
    due_date = serializers.DateTimeField(allow_null=True)
    is_completed = serializers.BooleanField()


class HomeDashboardSerializer(serializers.Serializer):
    user_summary = UserSummarySerializer()
    academic_progress = AcademicProgressSerializer()
    gamification = GamificationSerializer()
    upcoming_homework = UpcomingHomeworkSerializer()

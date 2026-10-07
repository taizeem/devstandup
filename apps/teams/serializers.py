import zoneinfo
from rest_framework import serializers
from .models import Team, TeamMember

class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = [
            "id",
            "name",
            "timezone",
            "standup_time",
            "webhook_url",
            "webhook_format",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_timezone(self, value: str) -> str:
        if value not in zoneinfo.available_timezones():
            raise serializers.ValidationError(f"Invalid IANA timezone: {value}")
        return value

class TeamMemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = TeamMember
        fields = [
            "id",
            "team",
            "user",
            "username",
            "display_name",
            "external_mention_id",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
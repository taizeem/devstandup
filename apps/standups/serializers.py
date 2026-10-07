from rest_framework import serializers
from .models import StandupEntry, StandupDigest
from apps.teams.models import TeamMember

class StandupEntrySubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StandupEntry
        fields = [
            "yesterday",
            "today",
            "blockers",
        ]

    def validate_yesterday(self, value: str) -> str:
        if not value or not value.strip():
            raise serializers.ValidationError("The 'yesterday' field cannot be blank.")
        return value.strip()

    def validate_today(self, value: str) -> str:
        if not value or not value.strip():
            raise serializers.ValidationError("The 'today' field cannot be blank.")
        return value.strip()

    def validate_blockers(self, value: str) -> str:
        return value.strip() if value else "None"

class StandupEntryDetailSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source="member.display_name", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)

    class Meta:
        model = StandupEntry
        fields = [
            "id",
            "team",
            "team_name",
            "member",
            "member_name",
            "standup_date",
            "yesterday",
            "today",
            "blockers",
            "is_late",
            "submitted_at",
            "updated_at",
        ]
        read_only_fields = fields

class StandupDigestSerializer(serializers.ModelSerializer):
    entries = StandupEntryDetailSerializer(many=True, read_only=True)

    class Meta:
        model = StandupDigest
        fields = [
            "id",
            "team",
            "digest_date",
            "compiled_at",
            "is_compiled",
            "missing_members_snapshot",
            "entries",
        ]
        read_only_fields = fields
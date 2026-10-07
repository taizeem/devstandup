import zoneinfo
from datetime import time
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

def validate_timezone(value: str):
    if value not in zoneinfo.available_timezones():
        raise ValidationError(f"'{value}' is not a valid IANA timezone.")

class WebhookFormat(models.TextChoices):
    SLACK = "SLACK", "Slack Incoming Webhook"
    DISCORD = "DISCORD", "Discord Webhook"
    GENERIC = "GENERIC", "Generic Readable Markdown"

class Team(models.Model):
    name = models.CharField(max_length=120, unique=True)
    timezone = models.CharField(
        max_length=64,
        default="UTC",
        validators=[validate_timezone],
        help_text="Standard IANA timezone name (e.g. 'America/New_York', 'Asia/Kolkata')."
    )
    standup_time = models.TimeField(
        default=time(hour=10, minute=0),
        help_text="Daily compilation deadline in the team's local timezone."
    )
    webhook_url = models.URLField(max_length=500)
    webhook_format = models.CharField(
        max_length=16,
        choices=WebhookFormat.choices,
        default=WebhookFormat.SLACK
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.timezone} @ {self.standup_time.strftime('%H:%M')})"

    def get_zoneinfo(self) -> zoneinfo.ZoneInfo:
        return zoneinfo.ZoneInfo(self.timezone)

class TeamMember(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_memberships"
    )
    display_name = models.CharField(max_length=100)
    external_mention_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="Optional Slack/Discord user ID (e.g., U12345 or <@!12345>) for tagging in digests."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="If inactive, the member is excluded from standup compilation & missing member checks."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["team", "user"], name="unique_team_user_membership")
        ]
        ordering = ["display_name"]

    def __str__(self) -> str:
        return f"{self.display_name} [{self.team.name}]"
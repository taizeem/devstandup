from django.db import models
from apps.teams.models import Team, TeamMember

class StandupDigest(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="digests")
    digest_date = models.DateField(help_text="The workday date this digest represents.")
    compiled_at = models.DateTimeField(null=True, blank=True)
    is_compiled = models.BooleanField(default=False)
    missing_members_snapshot = models.JSONField(
        default=list,
        blank=True,
        help_text="List of member names flagged as missing at compiled deadline."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["team", "digest_date"], name="unique_team_digest_date")
        ]
        ordering = ["-digest_date"]

    def __str__(self) -> str:
        status = "Compiled" if self.is_compiled else "Pending"
        return f"{self.team.name} - {self.digest_date} [{status}]"

class StandupEntry(models.Model):
    member = models.ForeignKey(TeamMember, on_delete=models.CASCADE, related_name="standups")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="standup_entries")
    digest = models.ForeignKey(
        StandupDigest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entries"
    )
    standup_date = models.DateField(help_text="Target workday date according to team local timezone.")
    yesterday = models.TextField(help_text="What I did since previous work day.")
    today = models.TextField(help_text="What I am doing today.")
    blockers = models.TextField(blank=True, default="", help_text="Blockers or 'None'.")
    is_late = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["member", "standup_date"],
                name="unique_member_standup_per_date"
            )
        ]
        ordering = ["-standup_date", "-submitted_at"]

    def __str__(self) -> str:
        late_indicator = " [LATE]" if self.is_late else ""
        return f"{self.member.display_name} - {self.standup_date}{late_indicator}"
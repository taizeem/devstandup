from datetime import time
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from apps.teams.models import Team, TeamMember, WebhookFormat

User = get_user_model()

class TeamModelSeniorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="secretpassword")

    def test_create_team_with_valid_iana_timezone(self):
        team = Team.objects.create(
            name="Platform Team",
            timezone="America/New_York",
            standup_time=time(9, 30),
            webhook_url="https://hooks.slack.com/services/T00/B00/X00"
        )
        self.assertEqual(team.timezone, "America/New_York")
        self.assertEqual(team.standup_time, time(9, 30))

    def test_invalid_timezone_raises_validation_error(self):
        team = Team.objects.create(
            name="SRE Team",
            timezone="Invalid/Atlantis_Zone",
            webhook_url="https://hooks.slack.com/services/T00/B00/X01"
        )
        with self.assertRaises(ValidationError):
            team.full_clean()

    def test_enforce_unique_team_user_membership(self):
        team = Team.objects.create(
            name="Security Team",
            timezone="UTC",
            webhook_url="https://hooks.slack.com/services/T00/B00/X02"
        )
        TeamMember.objects.create(
            team=team,
            user=self.user,
            display_name="Alice Sec"
        )
        with self.assertRaises(IntegrityError):
            TeamMember.objects.create(
                team=team,
                user=self.user,
                display_name="Alice Duplicate"
            )

    def test_multi_team_isolation(self):
        team_a = Team.objects.create(name="Team A", webhook_url="https://hook.a")
        team_b = Team.objects.create(name="Team B", webhook_url="https://hook.b")
        TeamMember.objects.create(team=team_a, user=self.user, display_name="Alice A")
        # Same user can belong to Team B
        member_b = TeamMember.objects.create(team=team_b, user=self.user, display_name="Alice B")
        self.assertEqual(member_b.team.name, "Team B")
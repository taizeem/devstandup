from datetime import date, time, datetime
from unittest.mock import patch
import zoneinfo
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.teams.models import Team, TeamMember
from apps.standups.models import StandupDigest, StandupEntry
from apps.standups.services.compilation import StandupCompilationService

User = get_user_model()

class StandupCompilationServiceSeniorTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(
            name="Backend Core",
            timezone="Asia/Kolkata",
            standup_time=time(10, 0),
            webhook_url="https://hooks.slack.com/services/mock"
        )
        self.user1 = User.objects.create_user("user1")
        self.user2 = User.objects.create_user("user2")
        self.user3 = User.objects.create_user("user3")

        self.m1 = TeamMember.objects.create(team=self.team, user=self.user1, display_name="Dev 1", is_active=True)
        self.m2 = TeamMember.objects.create(team=self.team, user=self.user2, display_name="Dev 2", is_active=True)
        # Inactive member should NEVER be flagged as missing
        self.m3 = TeamMember.objects.create(team=self.team, user=self.user3, display_name="Dev 3", is_active=False)

    @patch("apps.standups.services.webhook_dispatcher.WebhookDispatcher.send_digest")
    def test_missing_members_flagged_not_omitted(self, mock_webhook):
        mock_webhook.return_value = True
        target_date = date(2026, 10, 6)  # Tuesday

        # Only Dev 1 submits
        StandupEntry.objects.create(
            member=self.m1,
            team=self.team,
            standup_date=target_date,
            yesterday="Auth tests",
            today="Cache layer",
            blockers="None"
        )

        digest = StandupCompilationService.compile_team_digest(
            team=self.team,
            target_date=target_date,
            dispatch_webhook=True
        )

        self.assertTrue(digest.is_compiled)
        # Dev 2 is missing, Dev 3 is inactive so excluded
        self.assertIn("Dev 2", digest.missing_members_snapshot)
        self.assertNotIn("Dev 1", digest.missing_members_snapshot)
        self.assertNotIn("Dev 3", digest.missing_members_snapshot)
        self.assertEqual(len(digest.missing_members_snapshot), 1)
        mock_webhook.assert_called_once()

    def test_monday_previous_workday_calculation(self):
        monday = date(2026, 10, 5)
        friday = StandupCompilationService.get_previous_workday(monday)
        self.assertEqual(friday, date(2026, 10, 2))
        self.assertEqual(friday.weekday(), 4)

    def test_weekday_evaluation_skips_weekends(self):
        saturday = date(2026, 10, 10)
        sunday = date(2026, 10, 11)
        monday = date(2026, 10, 12)
        self.assertFalse(StandupCompilationService.is_weekday(saturday))
        self.assertFalse(StandupCompilationService.is_weekday(sunday))
        self.assertTrue(StandupCompilationService.is_weekday(monday))

    def test_should_compile_team_considers_timezones(self):
        # 10:00 AM Kolkata is 04:30 AM UTC
        # At 04:29 UTC -> False. At 04:31 UTC -> True
        dt_before = datetime(2026, 10, 6, 4, 29, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))
        dt_after = datetime(2026, 10, 6, 4, 31, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))

        self.assertFalse(StandupCompilationService.should_compile_team(self.team, dt_before))
        self.assertTrue(StandupCompilationService.should_compile_team(self.team, dt_after))
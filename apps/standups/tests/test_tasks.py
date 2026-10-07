from datetime import date, time
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from apps.teams.models import Team, TeamMember, WebhookFormat
from apps.standups.models import StandupDigest, StandupEntry
from apps.standups.services.webhook_dispatcher import WebhookDispatchError
from apps.standups.tasks import (
    check_and_compile_due_teams_task,
    compile_team_digest_task,
    dispatch_digest_webhook_task,
    dispatch_late_entry_webhook_task,
)

User = get_user_model()


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class CeleryTasksSeniorTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(
            name="Core Platform",
            timezone="UTC",
            standup_time=time(10, 0),
            webhook_url="https://hooks.slack.com/services/test",
            webhook_format=WebhookFormat.SLACK,
            is_active=True,
        )
        self.user = User.objects.create_user(username="alex")
        self.member = TeamMember.objects.create(
            team=self.team,
            user=self.user,
            display_name="Alex Lead",
            is_active=True,
        )

    @patch("apps.standups.services.compilation.StandupCompilationService.should_compile_team")
    @patch("apps.standups.tasks.compile_team_digest_task.delay")
    def test_heartbeat_task_fans_out_due_teams(self, mock_compile_delay, mock_should_compile):
        mock_should_compile.return_value = True

        enqueued_count = check_and_compile_due_teams_task()

        self.assertEqual(enqueued_count, 1)
        mock_compile_delay.assert_called_once_with(team_id=self.team.id)

    @patch("apps.standups.tasks.dispatch_digest_webhook_task.delay")
    def test_compile_team_digest_task_compiles_and_triggers_webhook(self, mock_dispatch_delay):
        digest_date = date(2026, 10, 7)
        digest_id = compile_team_digest_task(
            team_id=self.team.id,
            target_date_str=digest_date.isoformat(),
        )

        self.assertIsNotNone(digest_id)
        digest = StandupDigest.objects.get(id=digest_id)
        self.assertTrue(digest.is_compiled)
        self.assertIn("Alex Lead", digest.missing_members_snapshot)

        # Verifies async webhook dispatch was enqueued
        mock_dispatch_delay.assert_called_once_with(digest_id=digest.id)

    @patch("apps.standups.services.webhook_dispatcher.WebhookDispatcher.send_digest")
    def test_dispatch_digest_webhook_task_executes_successfully(self, mock_send_digest):
        mock_send_digest.return_value = True

        digest = StandupDigest.objects.create(
            team=self.team,
            digest_date=date(2026, 10, 7),
            is_compiled=True,
            missing_members_snapshot=[],
        )

        result = dispatch_digest_webhook_task(digest_id=digest.id)
        self.assertTrue(result)
        mock_send_digest.assert_called_once()

    @patch("apps.standups.services.webhook_dispatcher.WebhookDispatcher.send_late_entry")
    def test_dispatch_late_entry_webhook_task_executes_successfully(self, mock_send_late):
        mock_send_late.return_value = True

        entry = StandupEntry.objects.create(
            member=self.member,
            team=self.team,
            standup_date=date(2026, 10, 7),
            yesterday="Wrote migrations",
            today="Deploying workers",
            blockers="None",
            is_late=True,
        )

        result = dispatch_late_entry_webhook_task(entry_id=entry.id)
        self.assertTrue(result)
        mock_send_late.assert_called_once()

    @patch("apps.standups.services.webhook_dispatcher.WebhookDispatcher.send_digest")
    def test_webhook_task_retries_on_network_error(self, mock_send_digest):
        mock_send_digest.side_effect = WebhookDispatchError("Connection timed out")

        digest = StandupDigest.objects.create(
            team=self.team,
            digest_date=date(2026, 10, 7),
            is_compiled=True,
        )

        # In eager mode with max_retries, exhausting retries raises the exception
        with self.assertRaises(WebhookDispatchError):
            dispatch_digest_webhook_task(digest_id=digest.id)
import json
from datetime import date
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
import requests
from apps.teams.models import Team, TeamMember, WebhookFormat
from apps.standups.models import StandupDigest, StandupEntry
from apps.standups.services.webhook_dispatcher import WebhookDispatcher, WebhookDispatchError

User = get_user_model()


class WebhookDispatcherSeniorTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(
            name="DevOps Team",
            timezone="UTC",
            webhook_url="https://hooks.slack.com/services/valid",
            webhook_format=WebhookFormat.SLACK,
        )
        self.user = User.objects.create_user("charlie")
        self.member = TeamMember.objects.create(
            team=self.team,
            user=self.user,
            display_name="Charlie Root",
        )
        self.digest = StandupDigest.objects.create(
            team=self.team,
            digest_date=date(2026, 10, 6),
            is_compiled=True,
            missing_members_snapshot=["Dave"],
        )
        self.entry = StandupEntry.objects.create(
            member=self.member,
            team=self.team,
            digest=self.digest,
            standup_date=date(2026, 10, 6),
            yesterday="CI pipeline",
            today="Terraform upgrade",
            blockers="AWS quota",
        )

    @patch("requests.post")
    def test_slack_formatting_payload_structure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        success = WebhookDispatcher.send_digest(
            digest=self.digest,
            entries=[self.entry],
            missing_members=["Dave"],
        )
        self.assertTrue(success)
        mock_post.assert_called_once()

        # json.loads parses both bytes and str
        data = json.loads(mock_post.call_args[1]["data"])

        self.assertIn("blocks", data)
        self.assertEqual(data["blocks"][0]["type"], "header")
        self.assertIn("DevOps Team", data["blocks"][0]["text"]["text"])

        # Extract all text blocks to verify contents
        text_blocks = [
            b["text"]["text"]
            for b in data["blocks"]
            if "text" in b and isinstance(b["text"], dict) and "text" in b["text"]
        ]

        self.assertTrue(any("Charlie Root" in t for t in text_blocks))
        self.assertTrue(any("Terraform upgrade" in t for t in text_blocks))
        self.assertTrue(any("Missing Submissions" in t for t in text_blocks))
        self.assertTrue(any("`Dave`" in t for t in text_blocks))

    @patch("requests.post")
    def test_discord_formatting_payload_structure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        self.team.webhook_format = WebhookFormat.DISCORD
        self.team.save()

        success = WebhookDispatcher.send_digest(
            digest=self.digest,
            entries=[self.entry],
            missing_members=["Dave"],
        )
        self.assertTrue(success)
        mock_post.assert_called_once()

        data = json.loads(mock_post.call_args[1]["data"])

        self.assertIn("embeds", data)
        embed = data["embeds"][0]
        self.assertIn("DevOps Team", embed["title"])

        field_names = [f["name"] for f in embed["fields"]]
        self.assertIn("Charlie Root", field_names)
        self.assertIn("⚠️ Missing Submissions", field_names)

        missing_field = next(f for f in embed["fields"] if f["name"] == "⚠️ Missing Submissions")
        self.assertEqual(missing_field["value"], "Dave")

    @patch("apps.standups.services.webhook_dispatcher.logger.error")
    @patch("requests.post")
    def test_webhook_network_failure_raises_controlled_error(self, mock_post, mock_logger_error):
        mock_post.side_effect = requests.Timeout("Gateway Timeout")

        with self.assertRaises(WebhookDispatchError) as ctx:
            WebhookDispatcher.send_digest(
                digest=self.digest,
                entries=[self.entry],
                missing_members=["Dave"],
            )

        # 1. Verify our controlled domain exception was raised
        self.assertIn("Gateway Timeout", str(ctx.exception))

        # 2. Verify logger caught and recorded the error without leaking output to terminal
        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        self.assertIn("Webhook dispatch failed to %s: %s", args[0])
        self.assertTrue(kwargs.get("exc_info"))
from datetime import date, time
from unittest.mock import patch
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from apps.teams.models import Team, TeamMember
from apps.standups.models import StandupEntry, StandupDigest

User = get_user_model()

class StandupAPISeniorTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="password123")
        self.client.force_authenticate(user=self.user)

        self.team = Team.objects.create(
            name="Frontend Guild",
            timezone="UTC",
            standup_time=time(10, 0),
            webhook_url="https://hooks.slack.com/services/mock"
        )
        self.member = TeamMember.objects.create(
            team=self.team,
            user=self.user,
            display_name="Bob Builder",
            is_active=True
        )

    def test_post_standup_success(self):
        payload = {
            "yesterday": "Built design tokens",
            "today": "Refactoring Button component",
            "blockers": "Figma sync pending"
        }
        response = self.client.post(f"/api/v1/standups/submit/{self.team.id}/", payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["yesterday"], "Built design tokens")
        self.assertEqual(response.data["is_late"], False)

    def test_idempotent_submission_updates_existing_entry(self):
        payload_1 = {
            "yesterday": "Task A",
            "today": "Task B",
            "blockers": "None"
        }
        res1 = self.client.post(f"/api/v1/standups/submit/{self.team.id}/", payload_1)
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        payload_2 = {
            "yesterday": "Task A revised",
            "today": "Task B revised",
            "blockers": "None"
        }
        res2 = self.client.post(f"/api/v1/standups/submit/{self.team.id}/", payload_2)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(StandupEntry.objects.filter(member=self.member).count(), 1)
        self.assertEqual(StandupEntry.objects.get(member=self.member).yesterday, "Task A revised")

    @patch("apps.standups.services.webhook_dispatcher.WebhookDispatcher.send_late_entry")
    def test_post_late_standup_after_digest_compiled(self, mock_late_webhook):
        mock_late_webhook.return_value = True
        today = date.today()

        # Simulate digest already compiled at 10:00 AM
        digest = StandupDigest.objects.create(
            team=self.team,
            digest_date=today,
            is_compiled=True,
            missing_members_snapshot=["Bob Builder"]
        )

        payload = {
            "yesterday": "Debugging memory leak",
            "today": "Writing unit tests",
            "blockers": "None"
        }
        response = self.client.post(f"/api/v1/standups/submit/{self.team.id}/", payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_late"])

        digest.refresh_from_db()
        # Bob is now removed from missing members list and entry is appended
        self.assertNotIn("Bob Builder", digest.missing_members_snapshot)
        mock_late_webhook.assert_called_once()

    def test_history_queryable_by_person_and_date_range(self):
        StandupEntry.objects.create(
            member=self.member,
            team=self.team,
            standup_date=date(2026, 10, 1),
            yesterday="Y1",
            today="T1",
            blockers=""
        )
        StandupEntry.objects.create(
            member=self.member,
            team=self.team,
            standup_date=date(2026, 10, 2),
            yesterday="Y2",
            today="T2",
            blockers=""
        )
        StandupEntry.objects.create(
            member=self.member,
            team=self.team,
            standup_date=date(2026, 10, 6),
            yesterday="Y3",
            today="T3",
            blockers=""
        )

        # Filter by date range excluding Oct 6
        url = f"/api/v1/standups/history/?member_id={self.member.id}&start_date=2026-10-01&end_date=2026-10-02"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)
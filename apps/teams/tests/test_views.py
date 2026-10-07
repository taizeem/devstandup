from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from rest_framework import status
from apps.teams.models import Team

User = get_user_model()

class TeamAPISeniorTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="lead", password="leadpassword")
        self.client.force_authenticate(user=self.user)

    def test_create_team_validates_timezone_payload(self):
        payload = {
            "name": "Data Eng",
            "timezone": "Europe/London",
            "standup_time": "10:00:00",
            "webhook_url": "https://discord.com/api/webhooks/123/abc",
            "webhook_format": "DISCORD"
        }
        response = self.client.post("/api/v1/teams/groups/", payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Data Eng")

    def test_create_team_rejects_malformed_timezone(self):
        payload = {
            "name": "Data Eng 2",
            "timezone": "Invalid/Timezone",
            "standup_time": "10:00:00",
            "webhook_url": "https://discord.com/api/webhooks/123/abc",
        }
        response = self.client.post("/api/v1/teams/groups/", payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("timezone", response.data)
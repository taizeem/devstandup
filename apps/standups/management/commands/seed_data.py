from datetime import date, time
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.teams.models import Team, TeamMember, WebhookFormat
from apps.standups.models import StandupEntry, StandupDigest

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds database with demo teams, members, and partial standup submissions."

    def handle(self, *args, **options):
        self.stdout.write("Cleaning previous demo standup records...")
        StandupDigest.objects.all().delete()
        StandupEntry.objects.all().delete()

        # 1. Create Team A (Slack format) and Team B (Generic Markdown format)
        # We use httpbin.org/post so you can test real HTTP dispatches safely without Slack credentials
        team_backend, _ = Team.objects.update_or_create(
            name="Backend Core",
            defaults={
                "timezone": "Asia/Kolkata",
                "standup_time": time(10, 0),
                "webhook_url": "https://httpbin.org/post",
                "webhook_format": WebhookFormat.SLACK,
                "is_active": True,
            },
        )

        team_frontend, _ = Team.objects.update_or_create(
            name="Frontend Guild",
            defaults={
                "timezone": "America/New_York",
                "standup_time": time(10, 0),
                "webhook_url": "https://httpbin.org/post",
                "webhook_format": WebhookFormat.GENERIC,
                "is_active": True,
            },
        )

        # 2. Create Users
        users_data = [
            ("alice", "alice@example.com", "Alice Walker"),
            ("bob", "bob@example.com", "Bob Martin"),
            ("charlie", "charlie@example.com", "Charlie Root"),
            ("dana", "dana@example.com", "Dana Scott"),
        ]

        users = {}
        for username, email, full_name in users_data:
            user, _ = User.objects.get_or_create(username=username, defaults={"email": email})
            user.set_password("password123")
            user.save()
            users[username] = (user, full_name)

        # 3. Create Team Memberships for "Backend Core"
        # Alice & Bob: Active submitters
        m_alice, _ = TeamMember.objects.update_or_create(
            team=team_backend,
            user=users["alice"][0],
            defaults={"display_name": "Alice (Lead)", "is_active": True},
        )
        m_bob, _ = TeamMember.objects.update_or_create(
            team=team_backend,
            user=users["bob"][0],
            defaults={"display_name": "Bob (Backend)", "is_active": True},
        )
        # Charlie: Active, but has NOT submitted yet (will be flagged as missing!)
        m_charlie, _ = TeamMember.objects.update_or_create(
            team=team_backend,
            user=users["charlie"][0],
            defaults={"display_name": "Charlie (Junior)", "is_active": True},
        )
        # Dana: Inactive (on leave) -> should NOT be flagged as missing
        m_dana, _ = TeamMember.objects.update_or_create(
            team=team_backend,
            user=users["dana"][0],
            defaults={"display_name": "Dana (On Leave)", "is_active": False},
        )

        # 4. Populate Standup Submissions for Today (Alice and Bob only)
        today = date.today()

        StandupEntry.objects.create(
            member=m_alice,
            team=team_backend,
            standup_date=today,
            yesterday="Completed JWT rotation and schema migrations for auth service.",
            today="Reviewing PRs and profiling slow queries on the billing table.",
            blockers="Waiting on staging DB access approval.",
            is_late=False,
        )

        StandupEntry.objects.create(
            member=m_bob,
            team=team_backend,
            standup_date=today,
            yesterday="Implemented Redis cache fallback for user profile endpoints.",
            today="Adding automated test coverage for cache invalidation.",
            blockers="None",
            is_late=False,
        )

        self.stdout.write(self.style.SUCCESS("Demo data successfully seeded!"))
        self.stdout.write(
            f"Team '{team_backend.name}' (ID: {team_backend.id}):\n"
            f"  - Submitted on time: Alice, Bob\n"
            f"  - Expected to submit (Missing): Charlie\n"
            f"  - Inactive (Ignored): Dana\n"
        )
import os
import sys
import django
import requests
import os
from pathlib import Path
from dotenv import load_dotenv

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# Read webhook URL securely





from datetime import date, time
from django.contrib.auth import get_user_model
from apps.teams.models import Team, TeamMember, WebhookFormat
from apps.standups.models import StandupEntry, StandupDigest
from apps.standups.services.compilation import StandupCompilationService
from apps.standups.services.webhook_dispatcher import WebhookDispatcher

User = get_user_model()

# ==============================================================================
# PASTE YOUR EXACT DISCORD WEBHOOK URL HERE:
# ==============================================================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not DISCORD_WEBHOOK_URL:
    raise ValueError("Missing DISCORD_WEBHOOK_URL in .env file!")


def run_test():
    if "PASTE_YOUR_DISCORD" in DISCORD_WEBHOOK_URL:
        print("❌ ERROR: Please paste your real Discord webhook URL in the DISCORD_WEBHOOK_URL variable!")
        sys.exit(1)

    print("==================================================")
    print("🚀 STEP 0: Verifying Discord Webhook URL Reachability...")
    print("==================================================")
    try:
        ping_res = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": "🔌 Dev Standup Bot connected! Running live test flow..."},
            timeout=10,
        )
        if ping_res.status_code not in (200, 204):
            print(f"❌ Discord rejected the webhook! Status: {ping_res.status_code}, Body: {ping_res.text}")
            sys.exit(1)
        print("✅ Ping succeeded! Check Discord: you should see the connection message.")
    except Exception as e:
        print(f"❌ Failed to reach Discord: {e}")
        sys.exit(1)

    print("\n==================================================")
    print("👥 STEP 1: Setting up Team and Members...")
    print("==================================================")
    team, _ = Team.objects.update_or_create(
        name="Discord Core Team",
        defaults={
            "timezone": "UTC",
            "standup_time": time(10, 0),
            "webhook_url": DISCORD_WEBHOOK_URL,
            "webhook_format": WebhookFormat.DISCORD,
            "is_active": True,
        },
    )

    # Clean existing digests/entries for a fresh run
    today = date.today()
    StandupDigest.objects.filter(team=team, digest_date=today).delete()
    StandupEntry.objects.filter(team=team, standup_date=today).delete()

    # Create users & memberships
    users_info = [
        ("alice_discord", "Alice (Lead)"),
        ("bob_discord", "Bob (Backend)"),
        ("dave_discord", "Dave (Infra)"),
    ]
    members = {}
    for username, display_name in users_info:
        user, _ = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.com"})
        user.set_password("pass123")
        user.save()
        member, _ = TeamMember.objects.update_or_create(
            team=team,
            user=user,
            defaults={"display_name": display_name, "is_active": True},
        )
        members[username] = member

    print(f"✅ Team '{team.name}' ready with members: Alice, Bob, and Dave.")

    print("\n==================================================")
    print("📝 STEP 2: Creating On-Time Submissions (Alice & Bob)...")
    print("==================================================")
    # Alice submits
    StandupEntry.objects.create(
        member=members["alice_discord"],
        team=team,
        standup_date=today,
        yesterday="Merged PR #104: Timezone-aware compilation logic",
        today="Refactoring webhook serializers and test suites",
        blockers="None",
        is_late=False,
    )

    # Bob submits
    StandupEntry.objects.create(
        member=members["bob_discord"],
        team=team,
        standup_date=today,
        yesterday="Benchmarked row locking performance under SQLite and Postgres",
        today="Writing end-to-end integration tests",
        blockers="Waiting on staging DB credentials",
        is_late=False,
    )
    # NOTE: Dave has NOT submitted yet.

    print("✅ Submissions saved for Alice and Bob.")
    print("⚠️ Dave has not submitted and will be flagged as missing.")

    print("\n==================================================")
    print("📋 STEP 3: Compiling Standup Digest & Sending to Discord...")
    print("==================================================")
    digest = StandupCompilationService.compile_team_digest(
        team=team,
        target_date=today,
        dispatch_webhook=True,
    )

    print(f"✅ Digest #{digest.id} compiled successfully!")
    print(f"📊 Missing submitters flagged: {digest.missing_members_snapshot}")
    print("👉 CHECK DISCORD: You should now see the 'Standup Digest' card with Dave flagged as missing!")

    input("\n⏸️ Press ENTER to post Dave's LATE standup submission...")

    print("\n==================================================")
    print("⏰ STEP 4: Submitting Late Entry for Dave...")
    print("==================================================")
    late_entry = StandupEntry.objects.create(
        member=members["dave_discord"],
        team=team,
        digest=digest,
        standup_date=today,
        yesterday="Investigated cross-region network latency issues",
        today="Setting up Redis cluster and Celery Beat scheduler",
        blockers="None",
        is_late=True,
    )

    # Remove Dave from the missing members list in the database
    if "Dave (Infra)" in digest.missing_members_snapshot:
        digest.missing_members_snapshot.remove("Dave (Infra)")
        digest.save(update_fields=["missing_members_snapshot"])

    # Dispatch the late submission alert to Discord
    WebhookDispatcher.send_late_entry(late_entry)

    print("✅ Late submission posted!")
    print(f"📊 Updated Missing List in DB: {digest.missing_members_snapshot}")
    print("👉 CHECK DISCORD: You should now see the yellow 'Late Standup: Dave (Infra)' card!")
    print("\n🎉 Test completed successfully!")


if __name__ == "__main__":
    run_test()
from datetime import datetime, date, timedelta
from typing import Tuple, List, Optional
import zoneinfo
from django.utils import timezone
from django.db import transaction
from apps.teams.models import Team
from apps.standups.models import StandupDigest, StandupEntry
from .webhook_dispatcher import WebhookDispatcher

class StandupCompilationService:
    @staticmethod
    def get_team_local_time(team: Team, ref_dt: Optional[datetime] = None) -> datetime:
        dt = ref_dt or timezone.now()
        return dt.astimezone(team.get_zoneinfo())

    @staticmethod
    def is_weekday(target_date: date) -> bool:
        # Monday is 0 and Sunday is 6
        return target_date.weekday() < 5

    @staticmethod
    def get_previous_workday(current_date: date) -> date:
        # If Monday (0), previous workday was Friday (3 days prior)
        if current_date.weekday() == 0:
            return current_date - timedelta(days=3)
        # If Sunday (6), previous workday was Friday (2 days prior)
        elif current_date.weekday() == 6:
            return current_date - timedelta(days=2)
        else:
            return current_date - timedelta(days=1)

    @classmethod
    def should_compile_team(cls, team: Team, now_utc: Optional[datetime] = None) -> bool:
        if not team.is_active:
            return False

        team_now = cls.get_team_local_time(team, now_utc)
        today_date = team_now.date()

        # Only execute on workdays (Mon-Fri)
        if not cls.is_weekday(today_date):
            return False

        # Must have passed or reached scheduled standup time
        if team_now.time() < team.standup_time:
            return False

        # Has it already compiled for today?
        already_compiled = StandupDigest.objects.filter(
            team=team,
            digest_date=today_date,
            is_compiled=True
        ).exists()

        return not already_compiled

    @classmethod
    @transaction.atomic
    def compile_team_digest(
        cls,
        team: Team,
        target_date: Optional[date] = None,
        dispatch_webhook: bool = True
    ) -> StandupDigest:
        team_now = cls.get_team_local_time(team)
        digest_date = target_date or team_now.date()

        digest, _ = StandupDigest.objects.select_for_update().get_or_create(
            team=team,
            digest_date=digest_date
        )

        if digest.is_compiled:
            return digest

        # Active team members expected to submit
        active_members = list(team.members.filter(is_active=True))
        active_member_ids = {m.id for m in active_members}

        # Gather entries for this date
        entries = list(
            StandupEntry.objects.filter(
                team=team,
                standup_date=digest_date
            ).select_related("member")
        )

        submitted_member_ids = {e.member_id for e in entries}

        # Identify missing submitters
        missing_members: List[str] = [
            m.display_name for m in active_members if m.id not in submitted_member_ids
        ]

        # Associate entries with digest
        for entry in entries:
            if entry.digest_id != digest.id:
                entry.digest = digest
                entry.save(update_fields=["digest"])

        digest.is_compiled = True
        digest.compiled_at = timezone.now()
        digest.missing_members_snapshot = missing_members
        digest.save(update_fields=["is_compiled", "compiled_at", "missing_members_snapshot"])

        if dispatch_webhook and team.webhook_url:
            WebhookDispatcher.send_digest(
                digest=digest,
                entries=entries,
                missing_members=missing_members
            )

        return digest

    @classmethod
    def process_all_due_teams(cls) -> List[Tuple[Team, bool]]:
        now_utc = timezone.now()
        results = []
        teams = Team.objects.filter(is_active=True)

        for team in teams:
            if cls.should_compile_team(team, now_utc):
                try:
                    cls.compile_team_digest(team, dispatch_webhook=True)
                    results.append((team, True))
                except Exception:
                    results.append((team, False))
        return results
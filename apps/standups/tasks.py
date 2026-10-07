import logging
from datetime import date
from typing import Optional
from celery import shared_task
from django.utils import timezone
from apps.teams.models import Team
from apps.standups.models import StandupDigest, StandupEntry
from apps.standups.services.compilation import StandupCompilationService
from apps.standups.services.webhook_dispatcher import WebhookDispatcher, WebhookDispatchError

logger = logging.getLogger(__name__)


@shared_task(name="apps.standups.tasks.check_and_compile_due_teams_task")
def check_and_compile_due_teams_task():
    """
    Heartbeat task triggered by Celery Beat every minute.
    Identifies due teams and fans out compilation jobs to worker queues.
    """
    now_utc = timezone.now()
    active_teams = Team.objects.filter(is_active=True)
    enqueued_count = 0

    for team in active_teams:
        if StandupCompilationService.should_compile_team(team, now_utc):
            compile_team_digest_task.delay(team_id=team.id)
            enqueued_count += 1

    logger.info("Heartbeat scan complete. Enqueued %d teams for compilation.", enqueued_count)
    return enqueued_count


@shared_task(
    name="apps.standups.tasks.compile_team_digest_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def compile_team_digest_task(self, team_id: int, target_date_str: Optional[str] = None):
    """
    Atomically compiles a team's standup digest, then triggers async webhook dispatch.
    """
    try:
        team = Team.objects.get(id=team_id, is_active=True)
    except Team.DoesNotExist:
        logger.warning("Team with id=%d does not exist or is inactive. Skipping.", team_id)
        return None

    target_date = date.fromisoformat(target_date_str) if target_date_str else None

    try:
        # Compile digest without blocking on synchronous webhook dispatch
        digest = StandupCompilationService.compile_team_digest(
            team=team,
            target_date=target_date,
            dispatch_webhook=False,  # Delegated to async task below
        )

        # Trigger async webhook delivery
        dispatch_digest_webhook_task.delay(digest_id=digest.id)
        return digest.id
    except Exception as exc:
        logger.error("Error compiling digest for team_id=%d: %s", team_id, exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="apps.standups.tasks.dispatch_digest_webhook_task",
    bind=True,
    autoretry_for=(WebhookDispatchError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def dispatch_digest_webhook_task(self, digest_id: int):
    """
    Dispatches compiled digest to team webhook with exponential backoff on network failure.
    """
    try:
        digest = StandupDigest.objects.select_related("team").get(id=digest_id)
    except StandupDigest.DoesNotExist:
        logger.error("StandupDigest id=%d not found.", digest_id)
        return False

    entries = list(digest.entries.select_related("member").all())
    missing_members = digest.missing_members_snapshot or []

    WebhookDispatcher.send_digest(
        digest=digest,
        entries=entries,
        missing_members=missing_members,
    )
    logger.info("Digest id=%d successfully dispatched to team %s", digest_id, digest.team.name)
    return True


@shared_task(
    name="apps.standups.tasks.dispatch_late_entry_webhook_task",
    bind=True,
    autoretry_for=(WebhookDispatchError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def dispatch_late_entry_webhook_task(self, entry_id: int):
    """
    Dispatches individual late standup notification asynchronously.
    """
    try:
        entry = StandupEntry.objects.select_related("team", "member").get(id=entry_id)
    except StandupEntry.DoesNotExist:
        logger.error("StandupEntry id=%d not found.", entry_id)
        return False

    WebhookDispatcher.send_late_entry(entry)
    logger.info("Late entry id=%d successfully dispatched to %s", entry_id, entry.team.name)
    return True
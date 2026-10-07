from django.core.management.base import BaseCommand
from apps.teams.models import Team
from apps.standups.services.compilation import StandupCompilationService

class Command(BaseCommand):
    help = "Evaluates all teams and compiles standup digests due at team standup_time."

    def add_arguments(self, parser):
        parser.add_argument("--team-id", type=int, help="Force compile for a specific team ID.")
        parser.add_argument("--force", action="store_true", help="Bypass time/weekday validation checks.")

    def handle(self, *args, **options):
        team_id = options.get("team_id")
        force = options.get("force")

        if team_id:
            try:
                team = Team.objects.get(id=team_id)
                self.stdout.write(f"Compiling digest for team: {team.name}")
                digest = StandupCompilationService.compile_team_digest(team, dispatch_webhook=True)
                self.stdout.write(self.style.SUCCESS(f"Successfully compiled digest #{digest.id}"))
            except Team.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Team with ID {team_id} does not exist."))
            return

        if force:
            self.stdout.write("Force compiling all active teams...")
            for team in Team.objects.filter(is_active=True):
                digest = StandupCompilationService.compile_team_digest(team, dispatch_webhook=True)
                self.stdout.write(self.style.SUCCESS(f"Compiled for {team.name} (Digest #{digest.id})"))
            return

        self.stdout.write("Running periodic weekday check...")
        results = StandupCompilationService.process_all_due_teams()
        successful = sum(1 for _, ok in results if ok)
        self.stdout.write(
            self.style.SUCCESS(f"Compilation scan complete. Processed {successful}/{len(results)} due teams.")
        )
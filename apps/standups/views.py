from datetime import date
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.teams.models import TeamMember, Team
from .models import StandupEntry, StandupDigest
from .serializers import (
    StandupEntrySubmissionSerializer,
    StandupEntryDetailSerializer,
    StandupDigestSerializer,
)
from .services.compilation import StandupCompilationService
from .services.webhook_dispatcher import WebhookDispatcher

class StandupSubmissionAPIView(APIView):
    """
    Submits a standup entry for the authenticated user for the given team.
    Determines if submission is late based on team deadline & existing digest state.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, team_id: int):
        team = get_object_or_404(Team, id=team_id, is_active=True)
        member = get_object_or_404(
            TeamMember,
            team=team,
            user=request.user,
            is_active=True
        )

        serializer = StandupEntrySubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Team local time
        team_now = StandupCompilationService.get_team_local_time(team)
        target_date = team_now.date()

        # Check existing digest and determine if late
        digest = StandupDigest.objects.filter(team=team, digest_date=target_date).first()
        is_already_compiled = digest.is_compiled if digest else False
        is_past_deadline = team_now.time() >= team.standup_time
        is_late = is_already_compiled or is_past_deadline

        with transaction.atomic():
            entry, created = StandupEntry.objects.select_for_update().update_or_create(
                member=member,
                standup_date=target_date,
                defaults={
                    "team": team,
                    "yesterday": serializer.validated_data["yesterday"],
                    "today": serializer.validated_data["today"],
                    "blockers": serializer.validated_data.get("blockers", "None"),
                    "is_late": is_late,
                    "digest": digest,
                }
            )

            # If submitted late after the digest was compiled, append and dispatch a late update
            if is_late and digest and digest.is_compiled:
                # Remove from missing members if previously flagged
                if member.display_name in digest.missing_members_snapshot:
                    digest.missing_members_snapshot.remove(member.display_name)
                    digest.save(update_fields=["missing_members_snapshot"])

                WebhookDispatcher.send_late_entry(entry)

        response_serializer = StandupEntryDetailSerializer(entry)
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(response_serializer.data, status=response_status)

class StandupHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Queryable full history filtered by member and date range.
    GET /api/v1/standups/history/?member_id=X&team_id=Y&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    """
    serializer_class = StandupEntryDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = StandupEntry.objects.select_related("member", "team", "member__user").all()
        params = self.request.query_params

        team_id = params.get("team_id")
        if team_id:
            qs = qs.filter(team_id=team_id)

        member_id = params.get("member_id")
        if member_id:
            qs = qs.filter(member_id=member_id)

        start_date = params.get("start_date")
        if start_date:
            qs = qs.filter(standup_date__gte=start_date)

        end_date = params.get("end_date")
        if end_date:
            qs = qs.filter(standup_date__lte=end_date)

        is_late = params.get("is_late")
        if is_late is not None:
            qs = qs.filter(is_late=is_late.lower() in ["true", "1"])

        return qs

class TriggerDigestCompilationAPIView(APIView):
    """
    On-demand compilation trigger for a specific team.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, team_id: int):
        team = get_object_or_404(Team, id=team_id)
        target_date_str = request.data.get("date")
        target_date = date.fromisoformat(target_date_str) if target_date_str else None

        digest = StandupCompilationService.compile_team_digest(
            team=team,
            target_date=target_date,
            dispatch_webhook=True
        )
        return Response(StandupDigestSerializer(digest).data, status=status.HTTP_200_OK)
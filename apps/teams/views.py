from rest_framework import viewsets, permissions
from .models import Team, TeamMember
from .serializers import TeamSerializer, TeamMemberSerializer

class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["is_active"]
    search_fields = ["name"]

class TeamMemberViewSet(viewsets.ModelViewSet):
    queryset = TeamMember.objects.select_related("team", "user").all()
    serializer_class = TeamMemberSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        team_id = self.request.query_params.get("team_id")
        if team_id:
            qs = qs.filter(team_id=team_id)
        return qs
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TeamViewSet, TeamMemberViewSet

router = DefaultRouter()
router.register(r"groups", TeamViewSet, basename="team")
router.register(r"members", TeamMemberViewSet, basename="team-member")

urlpatterns = [
    path("", include(router.urls)),
]
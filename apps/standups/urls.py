from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StandupSubmissionAPIView,
    StandupHistoryViewSet,
    TriggerDigestCompilationAPIView,
)

router = DefaultRouter()
router.register(r"history", StandupHistoryViewSet, basename="standup-history")

urlpatterns = [
    path("submit/<int:team_id>/", StandupSubmissionAPIView.as_view(), name="standup-submit"),
    path("compile/<int:team_id>/", TriggerDigestCompilationAPIView.as_view(), name="standup-compile"),
    path("", include(router.urls)),
]
from django.urls import path

from . import api_views

urlpatterns = [
    path('agent/pair/', api_views.AgentPairView.as_view(), name='api_agent_pair'),
    path('agent/heartbeat/', api_views.AgentHeartbeatView.as_view(), name='api_agent_heartbeat'),
    path('agent/jobs/<uuid:job_id>/', api_views.AgentSignJobDetailView.as_view(), name='api_agent_job_detail'),
    path(
        'agent/jobs/<uuid:job_id>/complete/',
        api_views.AgentSignJobCompleteView.as_view(),
        name='api_agent_job_complete',
    ),
]

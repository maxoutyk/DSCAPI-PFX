from django.urls import path

from . import api_views, tenant_api_views

urlpatterns = [
    path('sign/usb/', tenant_api_views.UsbSignCreateView.as_view(), name='api_sign_usb_create'),
    path('sign/usb/<uuid:job_id>/', tenant_api_views.UsbSignDetailView.as_view(), name='api_sign_usb_detail'),
    path(
        'sign/usb/<uuid:job_id>/download/',
        tenant_api_views.UsbSignDownloadView.as_view(),
        name='api_sign_usb_download',
    ),
    path('agent/pair/', api_views.AgentPairView.as_view(), name='api_agent_pair'),
    path('agent/heartbeat/', api_views.AgentHeartbeatView.as_view(), name='api_agent_heartbeat'),
    path('agent/jobs/<uuid:job_id>/', api_views.AgentSignJobDetailView.as_view(), name='api_agent_job_detail'),
    path(
        'agent/jobs/<uuid:job_id>/complete/',
        api_views.AgentSignJobCompleteView.as_view(),
        name='api_agent_job_complete',
    ),
]

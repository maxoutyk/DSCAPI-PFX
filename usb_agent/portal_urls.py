from django.urls import path

from . import portal_views

urlpatterns = [
    path('dashboard/agent/', portal_views.agent_view, name='usb_agent'),
    path('dashboard/agent/pair/', portal_views.agent_pair_code_view, name='usb_agent_pair'),
    path('dashboard/agent/revoke/<int:device_id>/', portal_views.agent_revoke_view, name='usb_agent_revoke'),
    path('dashboard/sign/usb/', portal_views.sign_usb_view, name='usb_sign'),
    path('dashboard/sign/usb/<uuid:job_id>/pending/', portal_views.sign_usb_pending_view, name='usb_sign_pending'),
    path('dashboard/sign/usb/<uuid:job_id>/status/', portal_views.sign_usb_status_view, name='usb_sign_status'),
    path('dashboard/sign/usb/<uuid:job_id>/done/', portal_views.sign_usb_done_view, name='usb_sign_done'),
    path('dashboard/sign/usb/download/', portal_views.sign_usb_download_view, name='usb_sign_download'),
]

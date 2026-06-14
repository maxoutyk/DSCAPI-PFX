from django.urls import path

from . import portal_try, portal_views

urlpatterns = [
    path('dashboard/gst/', portal_views.gst_dashboard_view, name='gst_dashboard'),
    path('dashboard/gst/try/', portal_try.gst_portal_try_view, name='gst_portal_try'),
]

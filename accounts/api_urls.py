from django.urls import path

from .api_views import UsageReportApiView

urlpatterns = [
    path('usage/report/', UsageReportApiView.as_view(), name='api_usage_report'),
]

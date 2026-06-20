from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import APIKeyAuthentication
from accounts.models import TenantStatus
from accounts.permissions import IsAPIKeyAuthenticated
from accounts.usage_report_export import (
    UsageReportDownloadError,
    build_usage_report_download,
    build_usage_report_json,
)


class UsageReportApiView(APIView):
    """Download overall or customer-specific usage reports."""

    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated, IsAPIKeyAuthenticated]

    def get(self, request):
        tenant = request.user.tenant
        if tenant.status != TenantStatus.ACTIVE:
            return Response({'error': 'Account must be active.'}, status=status.HTTP_403_FORBIDDEN)

        period = request.query_params.get('period', '').strip() or None
        fmt = (request.query_params.get('export') or 'pdf').lower()
        scope = request.query_params.get('scope', '').strip().lower()
        bucket = request.query_params.get('bucket', '').strip()
        customer = request.query_params.get('customer', '').strip()
        api_key = request.user.api_key

        if not scope and not bucket and not customer:
            if api_key.customer_label:
                scope = 'customer'
                customer = api_key.customer_label
            else:
                scope = 'overall'
        elif not scope:
            scope = 'customer' if bucket or customer else 'overall'

        try:
            if fmt == 'json':
                body = build_usage_report_json(
                    tenant,
                    period=period,
                    scope=scope,
                    bucket=bucket,
                    customer_label=customer,
                )
                return Response(body)

            payload, content_type, filename = build_usage_report_download(
                tenant,
                period=period,
                scope=scope,
                bucket=bucket,
                customer_label=customer,
                fmt=fmt,
            )
        except UsageReportDownloadError as exc:
            return Response({'error': str(exc)}, status=exc.status_code)

        response = HttpResponse(payload, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

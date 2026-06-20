import base64

from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import APIKeyAuthentication
from accounts.permissions import IsAPIKeyAuthenticated

from .lookup_handlers import (
    execute_gst_eway_print,
    execute_gst_irn_print,
    execute_gst_preference,
    execute_gst_return_status,
    execute_gstin_search,
)
from .services import GstProfileIncompleteError, GstTenantNotActiveError, ensure_tenant_can_use_gst
from .throttling import GstLookupBurstThrottle, GstLookupUserThrottle


class TenantGstApiMixin:
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated, IsAPIKeyAuthenticated]
    throttle_classes = [GstLookupBurstThrottle, GstLookupUserThrottle]

    def get_tenant_and_api_key(self, request):
        return request.user.tenant, request.user.api_key

    def guard_request(self, request):
        tenant, api_key = self.get_tenant_and_api_key(request)
        try:
            ensure_tenant_can_use_gst(tenant)
        except GstTenantNotActiveError as exc:
            return None, None, Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except GstProfileIncompleteError as exc:
            return None, None, Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return tenant, api_key, None


def _pdf_api_response(request, code: int, body: dict):
    if code != status.HTTP_200_OK:
        return Response(body, status=code)
    wants_json = request.query_params.get('format') == 'json'
    if not wants_json and hasattr(request, 'data'):
        wants_json = request.data.get('format') == 'json'
    if wants_json:
        return Response(body, status=code)
    pdf_b64 = body.get('pdf_base64', '')
    if not pdf_b64:
        return Response({'error': 'PDF is not available.'}, status=status.HTTP_502_BAD_GATEWAY)
    pdf_bytes = base64.b64decode(pdf_b64)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = body.get('filename') or 'document.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _print_request_params(request):
    if request.method == 'POST':
        return request.data
    return request.query_params


class GstinSearchView(TenantGstApiMixin, APIView):
    endpoint_name = 'gst-gstin-search'

    def get(self, request):
        tenant, api_key, error = self.guard_request(request)
        if error is not None:
            return error

        code, body = execute_gstin_search(
            tenant=tenant,
            request=request,
            query_params=request.query_params,
            api_key=api_key,
        )
        return Response(body, status=code)


class GstPreferenceView(TenantGstApiMixin, APIView):
    endpoint_name = 'gst-preference'

    def get(self, request):
        tenant, api_key, error = self.guard_request(request)
        if error is not None:
            return error

        code, body = execute_gst_preference(
            tenant=tenant,
            request=request,
            query_params=request.query_params,
            api_key=api_key,
        )
        return Response(body, status=code)


class GstReturnStatusView(TenantGstApiMixin, APIView):
    endpoint_name = 'gst-return-status'

    def get(self, request):
        tenant, api_key, error = self.guard_request(request)
        if error is not None:
            return error

        code, body = execute_gst_return_status(
            tenant=tenant,
            request=request,
            query_params=request.query_params,
            api_key=api_key,
        )
        return Response(body, status=code)


class GstEwayPrintView(TenantGstApiMixin, APIView):
    endpoint_name = 'gst-eway-print'

    def get(self, request):
        return self._run(request)

    def post(self, request):
        return self._run(request)

    def _run(self, request):
        tenant, api_key, error = self.guard_request(request)
        if error is not None:
            return error

        code, body = execute_gst_eway_print(
            tenant=tenant,
            request=request,
            query_params=_print_request_params(request),
            api_key=api_key,
        )
        return _pdf_api_response(request, code, body)


class GstIrnPrintView(TenantGstApiMixin, APIView):
    endpoint_name = 'gst-irn-print'

    def get(self, request):
        return self._run(request)

    def post(self, request):
        return self._run(request)

    def _run(self, request):
        tenant, api_key, error = self.guard_request(request)
        if error is not None:
            return error

        code, body = execute_gst_irn_print(
            tenant=tenant,
            request=request,
            query_params=_print_request_params(request),
            api_key=api_key,
        )
        return _pdf_api_response(request, code, body)

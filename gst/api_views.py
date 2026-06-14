from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import APIKeyAuthentication
from accounts.permissions import IsAPIKeyAuthenticated

from .lookup_handlers import (
    execute_gst_preference,
    execute_gst_return_status,
    execute_gstin_search,
    GstPreferenceQuerySerializer,
    GstReturnStatusQuerySerializer,
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

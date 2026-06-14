"""Shared GST lookup execution for API and portal try-it."""

from __future__ import annotations

import re
from typing import Any

from rest_framework import serializers, status

from accounts.models import APIKey, Tenant
from signPdf.audit import get_client_ip

from .client import MyGSTCafeAPIError, MyGSTCafeConfigError, MyGSTCafeLookupClient
from .services import (
    GstGstinInvalidError,
    GstProfileIncompleteError,
    GstQuotaExceededError,
    GstTenantNotActiveError,
    ensure_gst_quota_remaining,
    ensure_tenant_can_use_gst,
    record_gst_api_call,
    resolve_tenant_gstin,
)

_FY_RE = re.compile(r'^[0-9]{4}-[0-9]{2}$')
_RETURN_TYPES = {'R1', 'R3B', 'R9'}


class GstPreferenceQuerySerializer(serializers.Serializer):
    gstin = serializers.CharField(required=False, allow_blank=True)
    fy = serializers.CharField()

    def validate_fy(self, value):
        fy = value.strip()
        if not _FY_RE.match(fy):
            raise serializers.ValidationError('Financial year must look like 2024-25.')
        return fy


class GstReturnStatusQuerySerializer(serializers.Serializer):
    gstin = serializers.CharField(required=False, allow_blank=True)
    fy = serializers.CharField()
    type = serializers.CharField(required=False, allow_blank=True)

    def validate_fy(self, value):
        fy = value.strip()
        if not _FY_RE.match(fy):
            raise serializers.ValidationError('Financial year must look like 2024-25.')
        return fy

    def validate_type(self, value):
        normalized = (value or '').strip().upper()
        if normalized and normalized not in _RETURN_TYPES:
            raise serializers.ValidationError('Return type must be one of R1, R3B, or R9.')
        return normalized


def _guard_tenant(tenant: Tenant) -> tuple[int, dict[str, Any]] | None:
    try:
        ensure_tenant_can_use_gst(tenant)
    except GstTenantNotActiveError as exc:
        return status.HTTP_403_FORBIDDEN, {'error': str(exc)}
    except GstProfileIncompleteError as exc:
        return status.HTTP_403_FORBIDDEN, {'error': str(exc)}
    return None


def _resolve_gstin(tenant: Tenant, requested: str | None) -> tuple[str | None, tuple[int, dict[str, Any]] | None]:
    try:
        return resolve_tenant_gstin(tenant, requested), None
    except GstGstinInvalidError as exc:
        return None, (status.HTTP_400_BAD_REQUEST, {'error': str(exc)})


def execute_gstin_search(
    *,
    tenant: Tenant,
    request,
    query_params: dict[str, Any],
    api_key: APIKey | None = None,
) -> tuple[int, dict[str, Any]]:
    blocked = _guard_tenant(tenant)
    if blocked:
        return blocked

    requested = (query_params.get('gstin') or '').strip()
    gstin, gstin_error = _resolve_gstin(tenant, requested or None)
    if gstin_error:
        return gstin_error

    client_ip = get_client_ip(request)
    try:
        ensure_gst_quota_remaining(tenant)
    except GstQuotaExceededError as exc:
        return status.HTTP_429_TOO_MANY_REQUESTS, {'error': str(exc)}

    try:
        payload = MyGSTCafeLookupClient().get_gstin_details(gstin)
    except MyGSTCafeConfigError as exc:
        return status.HTTP_503_SERVICE_UNAVAILABLE, {'error': str(exc)}
    except MyGSTCafeAPIError as exc:
        record_gst_api_call(
            tenant,
            endpoint='gst-gstin-search',
            success=False,
            api_key=api_key,
            client_ip=client_ip,
            gstin=gstin,
            meta={'status_code': exc.status_code},
        )
        code = status.HTTP_502_BAD_GATEWAY
        if exc.status_code and 400 <= exc.status_code < 500:
            code = status.HTTP_400_BAD_REQUEST
        return code, {'error': str(exc)}

    try:
        record_gst_api_call(
            tenant,
            endpoint='gst-gstin-search',
            success=True,
            api_key=api_key,
            client_ip=client_ip,
            gstin=gstin,
        )
    except GstQuotaExceededError as exc:
        return status.HTTP_429_TOO_MANY_REQUESTS, {'error': str(exc)}

    return status.HTTP_200_OK, {'gstin': gstin, 'data': payload}


def execute_gst_preference(
    *,
    tenant: Tenant,
    request,
    query_params: dict[str, Any],
    api_key: APIKey | None = None,
) -> tuple[int, dict[str, Any]]:
    blocked = _guard_tenant(tenant)
    if blocked:
        return blocked

    serializer = GstPreferenceQuerySerializer(data=query_params)
    if not serializer.is_valid():
        return status.HTTP_400_BAD_REQUEST, serializer.errors

    gstin, gstin_error = _resolve_gstin(tenant, serializer.validated_data.get('gstin') or None)
    if gstin_error:
        return gstin_error

    fy = serializer.validated_data['fy']
    client_ip = get_client_ip(request)
    try:
        ensure_gst_quota_remaining(tenant)
    except GstQuotaExceededError as exc:
        return status.HTTP_429_TOO_MANY_REQUESTS, {'error': str(exc)}

    try:
        payload = MyGSTCafeLookupClient().get_preference(gstin, fy)
    except MyGSTCafeConfigError as exc:
        return status.HTTP_503_SERVICE_UNAVAILABLE, {'error': str(exc)}
    except MyGSTCafeAPIError as exc:
        record_gst_api_call(
            tenant,
            endpoint='gst-preference',
            success=False,
            api_key=api_key,
            client_ip=client_ip,
            gstin=gstin,
            meta={'fy': fy, 'status_code': exc.status_code},
        )
        code = status.HTTP_502_BAD_GATEWAY
        if exc.status_code and 400 <= exc.status_code < 500:
            code = status.HTTP_400_BAD_REQUEST
        return code, {'error': str(exc)}

    try:
        record_gst_api_call(
            tenant,
            endpoint='gst-preference',
            success=True,
            api_key=api_key,
            client_ip=client_ip,
            gstin=gstin,
            meta={'fy': fy},
        )
    except GstQuotaExceededError as exc:
        return status.HTTP_429_TOO_MANY_REQUESTS, {'error': str(exc)}

    return status.HTTP_200_OK, {'gstin': gstin, 'fy': fy, 'data': payload}


def execute_gst_return_status(
    *,
    tenant: Tenant,
    request,
    query_params: dict[str, Any],
    api_key: APIKey | None = None,
) -> tuple[int, dict[str, Any]]:
    blocked = _guard_tenant(tenant)
    if blocked:
        return blocked

    serializer = GstReturnStatusQuerySerializer(data=query_params)
    if not serializer.is_valid():
        return status.HTTP_400_BAD_REQUEST, serializer.errors

    gstin, gstin_error = _resolve_gstin(tenant, serializer.validated_data.get('gstin') or None)
    if gstin_error:
        return gstin_error

    fy = serializer.validated_data['fy']
    return_type = serializer.validated_data.get('type') or ''
    client_ip = get_client_ip(request)
    if not client_ip:
        return status.HTTP_400_BAD_REQUEST, {
            'error': 'Client IP could not be determined for return status lookup.',
        }

    try:
        ensure_gst_quota_remaining(tenant)
    except GstQuotaExceededError as exc:
        return status.HTTP_429_TOO_MANY_REQUESTS, {'error': str(exc)}

    try:
        payload = MyGSTCafeLookupClient().get_return_status(
            gstin,
            fy,
            return_type=return_type,
            client_ip=client_ip,
        )
    except MyGSTCafeConfigError as exc:
        return status.HTTP_503_SERVICE_UNAVAILABLE, {'error': str(exc)}
    except MyGSTCafeAPIError as exc:
        record_gst_api_call(
            tenant,
            endpoint='gst-return-status',
            success=False,
            api_key=api_key,
            client_ip=client_ip,
            gstin=gstin,
            meta={'fy': fy, 'type': return_type, 'status_code': exc.status_code},
        )
        code = status.HTTP_502_BAD_GATEWAY
        if exc.status_code and 400 <= exc.status_code < 500:
            code = status.HTTP_400_BAD_REQUEST
        return code, {'error': str(exc)}

    try:
        record_gst_api_call(
            tenant,
            endpoint='gst-return-status',
            success=True,
            api_key=api_key,
            client_ip=client_ip,
            gstin=gstin,
            meta={'fy': fy, 'type': return_type},
        )
    except GstQuotaExceededError as exc:
        return status.HTTP_429_TOO_MANY_REQUESTS, {'error': str(exc)}

    return status.HTTP_200_OK, {
        'gstin': gstin,
        'fy': fy,
        'type': return_type or None,
        'data': payload,
    }


PORTAL_ENDPOINTS = {
    'gst-gstin-search': execute_gstin_search,
    'gst-preference': execute_gst_preference,
    'gst-return-status': execute_gst_return_status,
}


def execute_portal_endpoint(
    *,
    endpoint_id: str,
    tenant: Tenant,
    request,
    query_params: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    handler = PORTAL_ENDPOINTS.get(endpoint_id)
    if handler is None:
        return status.HTTP_400_BAD_REQUEST, {'error': 'Unknown endpoint.'}
    return handler(tenant=tenant, request=request, query_params=query_params, api_key=None)

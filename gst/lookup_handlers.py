"""Shared GST lookup execution for API and portal try-it."""

from __future__ import annotations

import base64
import re
from typing import Any

from rest_framework import serializers, status

from accounts.models import APIKey, Tenant
from accounts.services import NicPortalCredentialsMissingError, get_company_profile, get_nic_portal_credentials
from signPdf.audit import get_client_ip

from .client import MyGSTCafeAPIError, MyGSTCafeConfigError, MyGSTCafeLookupClient
from .print_client import MyGSTCafePrintClient
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
from .validation import is_valid_ewb_number, is_valid_irn, normalize_ewb_number, normalize_irn

_FY_RE = re.compile(r'^[0-9]{4}-[0-9]{2}$')
_RETURN_TYPES = {'R1', 'R3B', 'R9'}
_SENSITIVE_META_KEYS = frozenset({
    'password',
    'username',
    'nicPassword',
    'nicUsername',
    'api_secret',
    'apiSecret',
})


def _sanitize_partner_meta(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    return {
        key: value
        for key, value in payload.items()
        if str(key) not in _SENSITIVE_META_KEYS
    }


def _api_gstin_override_allowed(api_key: APIKey | None) -> bool:
    return api_key is not None


def _api_nic_override_allowed(api_key: APIKey | None) -> bool:
    from django.conf import settings

    return api_key is not None and getattr(settings, 'GST_ALLOW_NIC_API_OVERRIDES', False)


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


def _resolve_nic_credentials(
    tenant: Tenant,
    *,
    username_override: str | None = None,
    password_override: str | None = None,
    allow_overrides: bool = False,
) -> tuple[tuple[str, str] | None, tuple[int, dict[str, Any]] | None]:
    if allow_overrides and username_override and password_override:
        return (username_override, password_override), None

    profile = get_company_profile(tenant)
    try:
        return get_nic_portal_credentials(profile), None
    except NicPortalCredentialsMissingError:
        if allow_overrides:
            return None, (
                status.HTTP_403_FORBIDDEN,
                {
                    'error': (
                        'NIC portal credentials are not configured. Pass nicUsername and nicPassword '
                        'in the API request or save them on your company profile.'
                    ),
                },
            )
        return None, (
            status.HTTP_403_FORBIDDEN,
            {
                'error': (
                    'NIC portal credentials are not configured. Add them on your company profile '
                    'to download E-way bills and e-invoice PDFs.'
                ),
            },
        )


def _partner_error_http_status(exc: MyGSTCafeAPIError) -> int:
    if exc.status_code == 503:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if exc.status_code and 400 <= exc.status_code < 500:
        return status.HTTP_400_BAD_REQUEST
    return status.HTTP_502_BAD_GATEWAY


def _pdf_success_payload(*, gstin: str, filename: str, pdf_bytes: bytes, **extra: Any) -> dict[str, Any]:
    payload = {
        'gstin': gstin,
        'filename': filename,
        'content_type': 'application/pdf',
        'pdf_base64': base64.b64encode(pdf_bytes).decode('ascii'),
    }
    payload.update(extra)
    return payload


class GstPrintRequestSerializerMixin(serializers.Serializer):
    gstin = serializers.CharField(required=False, allow_blank=True)
    nicUsername = serializers.CharField(required=False, allow_blank=True)
    nicPassword = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        username = (attrs.get('nicUsername') or '').strip()
        password = attrs.get('nicPassword') or ''
        has_username = bool(username)
        has_password = bool(password)
        if has_username != has_password:
            raise serializers.ValidationError(
                'nicUsername and nicPassword must both be provided when passing NIC credentials in the request.',
            )
        if has_username:
            attrs['nicUsername'] = username
            attrs['nicPassword'] = password
        else:
            attrs.pop('nicUsername', None)
            attrs.pop('nicPassword', None)

        gstin = (attrs.get('gstin') or '').strip()
        if gstin:
            attrs['gstin'] = gstin
        else:
            attrs.pop('gstin', None)
        return attrs


class GstEwayPrintQuerySerializer(GstPrintRequestSerializerMixin, serializers.Serializer):
    ewbNumber = serializers.CharField()

    def validate_ewbNumber(self, value):
        normalized = normalize_ewb_number(value)
        if not is_valid_ewb_number(normalized):
            raise serializers.ValidationError('E-way bill number must be a 12-digit number.')
        return normalized


class GstIrnPrintQuerySerializer(GstPrintRequestSerializerMixin, serializers.Serializer):
    irn = serializers.CharField()

    def validate_irn(self, value):
        normalized = normalize_irn(value)
        if not is_valid_irn(normalized):
            raise serializers.ValidationError('IRN must be a 64-character hexadecimal string.')
        return normalized


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
            meta={'status_code': exc.status_code, 'partner_error': _sanitize_partner_meta(exc.payload or {})},
        )
        return _partner_error_http_status(exc), {'error': str(exc)}

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
            meta={'fy': fy, 'status_code': exc.status_code, 'partner_error': _sanitize_partner_meta(exc.payload or {})},
        )
        return _partner_error_http_status(exc), {'error': str(exc)}

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
            meta={'fy': fy, 'type': return_type, 'status_code': exc.status_code, 'partner_error': _sanitize_partner_meta(exc.payload or {})},
        )
        return _partner_error_http_status(exc), {'error': str(exc)}

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


def execute_gst_eway_print(
    *,
    tenant: Tenant,
    request,
    query_params: dict[str, Any],
    api_key: APIKey | None = None,
) -> tuple[int, dict[str, Any]]:
    blocked = _guard_tenant(tenant)
    if blocked:
        return blocked

    serializer = GstEwayPrintQuerySerializer(data=query_params)
    if not serializer.is_valid():
        return status.HTTP_400_BAD_REQUEST, serializer.errors

    validated = serializer.validated_data
    allow_gstin_override = _api_gstin_override_allowed(api_key)
    allow_nic_override = _api_nic_override_allowed(api_key)
    requested_gstin = validated.get('gstin') if allow_gstin_override else None
    gstin, gstin_error = _resolve_gstin(tenant, requested_gstin)
    if gstin_error:
        return gstin_error

    ewb_number = validated['ewbNumber']
    client_ip = get_client_ip(request)
    nic_creds, nic_error = _resolve_nic_credentials(
        tenant,
        username_override=validated.get('nicUsername') if allow_nic_override else None,
        password_override=validated.get('nicPassword') if allow_nic_override else None,
        allow_overrides=allow_nic_override,
    )
    if nic_error:
        return nic_error
    nic_username, nic_password = nic_creds
    try:
        ensure_gst_quota_remaining(tenant)
    except GstQuotaExceededError as exc:
        return status.HTTP_429_TOO_MANY_REQUESTS, {'error': str(exc)}

    try:
        pdf_bytes = MyGSTCafePrintClient().get_eway_detailed_print(
            ewb_number,
            gstin,
            nic_username=nic_username,
            nic_password=nic_password,
        )
    except MyGSTCafeConfigError as exc:
        return status.HTTP_503_SERVICE_UNAVAILABLE, {'error': str(exc)}
    except MyGSTCafeAPIError as exc:
        record_gst_api_call(
            tenant,
            endpoint='gst-eway-print',
            success=False,
            api_key=api_key,
            client_ip=client_ip,
            gstin=gstin,
            meta={'ewb_number': ewb_number, 'status_code': exc.status_code, 'partner_error': _sanitize_partner_meta(exc.payload or {})},
        )
        return _partner_error_http_status(exc), {'error': str(exc)}

    try:
        record_gst_api_call(
            tenant,
            endpoint='gst-eway-print',
            success=True,
            api_key=api_key,
            client_ip=client_ip,
            gstin=gstin,
            meta={'ewb_number': ewb_number},
        )
    except GstQuotaExceededError as exc:
        return status.HTTP_429_TOO_MANY_REQUESTS, {'error': str(exc)}

    return status.HTTP_200_OK, _pdf_success_payload(
        gstin=gstin,
        filename=f'eway-{ewb_number}.pdf',
        pdf_bytes=pdf_bytes,
        ewb_number=ewb_number,
    )


def execute_gst_irn_print(
    *,
    tenant: Tenant,
    request,
    query_params: dict[str, Any],
    api_key: APIKey | None = None,
) -> tuple[int, dict[str, Any]]:
    blocked = _guard_tenant(tenant)
    if blocked:
        return blocked

    serializer = GstIrnPrintQuerySerializer(data=query_params)
    if not serializer.is_valid():
        return status.HTTP_400_BAD_REQUEST, serializer.errors

    validated = serializer.validated_data
    allow_gstin_override = _api_gstin_override_allowed(api_key)
    allow_nic_override = _api_nic_override_allowed(api_key)
    requested_gstin = validated.get('gstin') if allow_gstin_override else None
    gstin, gstin_error = _resolve_gstin(tenant, requested_gstin)
    if gstin_error:
        return gstin_error

    irn = validated['irn']
    client_ip = get_client_ip(request)
    nic_creds, nic_error = _resolve_nic_credentials(
        tenant,
        username_override=validated.get('nicUsername') if allow_nic_override else None,
        password_override=validated.get('nicPassword') if allow_nic_override else None,
        allow_overrides=allow_nic_override,
    )
    if nic_error:
        return nic_error
    nic_username, nic_password = nic_creds
    try:
        ensure_gst_quota_remaining(tenant)
    except GstQuotaExceededError as exc:
        return status.HTTP_429_TOO_MANY_REQUESTS, {'error': str(exc)}

    try:
        pdf_bytes = MyGSTCafePrintClient().get_einvoice_pdf(
            irn,
            gstin,
            nic_username=nic_username,
            nic_password=nic_password,
        )
    except MyGSTCafeConfigError as exc:
        return status.HTTP_503_SERVICE_UNAVAILABLE, {'error': str(exc)}
    except MyGSTCafeAPIError as exc:
        record_gst_api_call(
            tenant,
            endpoint='gst-irn-print',
            success=False,
            api_key=api_key,
            client_ip=client_ip,
            gstin=gstin,
            meta={'irn_prefix': irn[:8], 'status_code': exc.status_code, 'partner_error': _sanitize_partner_meta(exc.payload or {})},
        )
        return _partner_error_http_status(exc), {'error': str(exc)}

    try:
        record_gst_api_call(
            tenant,
            endpoint='gst-irn-print',
            success=True,
            api_key=api_key,
            client_ip=client_ip,
            gstin=gstin,
            meta={'irn_prefix': irn[:8]},
        )
    except GstQuotaExceededError as exc:
        return status.HTTP_429_TOO_MANY_REQUESTS, {'error': str(exc)}

    return status.HTTP_200_OK, _pdf_success_payload(
        gstin=gstin,
        filename=f'einvoice-{irn[:8]}.pdf',
        pdf_bytes=pdf_bytes,
        irn=irn,
    )


PORTAL_ENDPOINTS = {
    'gst-gstin-search': execute_gstin_search,
    'gst-preference': execute_gst_preference,
    'gst-return-status': execute_gst_return_status,
    'gst-eway-print': execute_gst_eway_print,
    'gst-irn-print': execute_gst_irn_print,
}


_PORTAL_STRIPPED_PARAMS = frozenset({'nicUsername', 'nicPassword'})
_PRINT_PORTAL_STRIPPED_PARAMS = _PORTAL_STRIPPED_PARAMS | frozenset({'gstin'})


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
    strip_keys = (
        _PRINT_PORTAL_STRIPPED_PARAMS
        if endpoint_id in {'gst-eway-print', 'gst-irn-print'}
        else _PORTAL_STRIPPED_PARAMS
    )
    sanitized = {
        key: value
        for key, value in query_params.items()
        if key not in strip_keys
    }
    return handler(tenant=tenant, request=request, query_params=sanitized, api_key=None)

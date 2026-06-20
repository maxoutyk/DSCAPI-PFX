from django.db import transaction

from accounts.models import APIKey, Tenant, TenantStatus
from accounts.quota import QuotaExceededError, consume_quota
from accounts.services import ensure_tenant_quota_remaining, get_company_profile

from .models import GstApiLog
from .validation import is_valid_gstin, normalize_gstin

# GST uses the shared tenant monthly quota (same counter as signing/USB).
GstQuotaExceededError = QuotaExceededError


class GstProfileIncompleteError(Exception):
    pass


class GstTenantNotActiveError(Exception):
    pass


class GstGstinInvalidError(Exception):
    pass


def ensure_tenant_can_use_gst(tenant: Tenant):
    if tenant.status != TenantStatus.ACTIVE:
        if tenant.status == TenantStatus.PENDING_EMAIL:
            raise GstTenantNotActiveError('Verify your email before using GST services.')
        if tenant.status == TenantStatus.PENDING_APPROVAL:
            raise GstTenantNotActiveError('Your account is awaiting admin approval.')
        if tenant.status == TenantStatus.SUSPENDED:
            raise GstTenantNotActiveError('Your account has been suspended.')
        raise GstTenantNotActiveError('Your account is not active.')

    profile = get_company_profile(tenant)
    if not profile.is_complete:
        raise GstProfileIncompleteError(
            'Complete your company profile before using GST services.'
        )


def ensure_gst_quota_remaining(tenant: Tenant) -> None:
    """Reject before calling the partner when the shared monthly quota is exhausted."""
    ensure_tenant_quota_remaining(tenant)


def resolve_tenant_gstin(tenant: Tenant, requested_gstin: str | None = None) -> str:
    profile = get_company_profile(tenant)
    tenant_gstin = normalize_gstin(profile.gstin)
    if not requested_gstin:
        if not tenant_gstin or not is_valid_gstin(tenant_gstin):
            raise GstGstinInvalidError(
                'Your company profile has an invalid GSTIN. Update it before using GST services.'
            )
        return tenant_gstin
    normalized = normalize_gstin(requested_gstin)
    if not is_valid_gstin(normalized):
        raise GstGstinInvalidError('Enter a valid 15-character GSTIN.')
    return normalized


@transaction.atomic
def record_gst_api_call(
    tenant: Tenant,
    *,
    endpoint: str,
    success: bool,
    api_key: APIKey | None = None,
    client_ip: str | None = None,
    gstin: str = '',
    meta: dict | None = None,
) -> GstApiLog:
    tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
    if success:
        consume_quota(tenant)

    return GstApiLog.objects.create(
        tenant=tenant,
        endpoint=endpoint,
        success=success,
        gstin=gstin,
        client_ip=client_ip,
        api_key=api_key,
        meta=meta or {},
    )

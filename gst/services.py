from django.db import transaction

from accounts.models import APIKey, Tenant, TenantStatus
from accounts.services import get_company_profile

from .models import GstApiLog
from .validation import is_valid_gstin, normalize_gstin


class GstQuotaExceededError(Exception):
    pass


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


@transaction.atomic
def ensure_gst_quota_remaining(tenant: Tenant) -> None:
    """Reject before calling the partner when monthly quota is exhausted."""
    tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
    tenant.reset_quota_if_needed()
    if tenant.gst_usage_this_month >= tenant.gst_monthly_quota:
        raise GstQuotaExceededError(
            f'Monthly GST quota exceeded ({tenant.gst_monthly_quota} calls/month).'
        )


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
    tenant.reset_quota_if_needed()
    if success:
        if tenant.gst_usage_this_month >= tenant.gst_monthly_quota:
            raise GstQuotaExceededError(
                f'Monthly GST quota exceeded ({tenant.gst_monthly_quota} calls/month).'
            )
        tenant.gst_usage_this_month += 1
        tenant.save(update_fields=['gst_usage_this_month', 'updated_at'])

    return GstApiLog.objects.create(
        tenant=tenant,
        endpoint=endpoint,
        success=success,
        gstin=gstin,
        client_ip=client_ip,
        api_key=api_key,
        meta=meta or {},
    )

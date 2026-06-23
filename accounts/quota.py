"""Centralized tenant quota: Free (monthly), Pro (term), Pro+ (term with carry on renewal)."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    QuotaEntitlement,
    QuotaEntitlementStatus,
    QuotaPlan,
    Tenant,
)


class QuotaExceededError(Exception):
    pass


@dataclass(frozen=True)
class QuotaState:
    plan: str
    limit: int
    used: int
    remaining: int
    period_label: str
    resets_or_expires_at: datetime
    is_term_based: bool
    carry_forward: int = 0
    purchased_limit: int | None = None
    entitlement_id: int | None = None
    can_carry_on_renewal: bool = False

    @property
    def is_free(self) -> bool:
        return self.plan == QuotaPlan.FREE


def add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day, hour=0, minute=0, second=0, microsecond=0)


def _free_quota_state(tenant: Tenant) -> QuotaState:
    tenant.reset_quota_if_needed()
    limit = tenant.monthly_quota
    used = tenant.usage_this_month
    return QuotaState(
        plan=QuotaPlan.FREE,
        limit=limit,
        used=used,
        remaining=max(0, limit - used),
        period_label='This month',
        resets_or_expires_at=tenant.quota_reset_at,
        is_term_based=False,
    )


def _expire_entitlement(entitlement: QuotaEntitlement, *, tenant: Tenant) -> None:
    entitlement.status = QuotaEntitlementStatus.EXPIRED
    entitlement.save(update_fields=['status', 'updated_at'])
    if tenant.quota_plan != QuotaPlan.FREE:
        tenant.quota_plan = QuotaPlan.FREE
        tenant.save(update_fields=['quota_plan', 'updated_at'])


def _active_entitlement_queryset(tenant: Tenant):
    return QuotaEntitlement.objects.filter(
        tenant=tenant,
        status=QuotaEntitlementStatus.ACTIVE,
    ).order_by('-starts_at')


def _get_locked_active_entitlement(tenant: Tenant) -> QuotaEntitlement | None:
    entitlement = _active_entitlement_queryset(tenant).select_for_update().first()
    if entitlement is None:
        return None
    now = timezone.now()
    if now >= entitlement.ends_at:
        _expire_entitlement(entitlement, tenant=tenant)
        return None
    return entitlement


def _term_quota_state(tenant: Tenant, entitlement: QuotaEntitlement) -> QuotaState:
    limit = entitlement.quota_limit
    used = entitlement.usage_count
    remaining = max(0, limit - used)
    plan = entitlement.plan_at_grant
    now = timezone.now()
    return QuotaState(
        plan=plan,
        limit=limit,
        used=used,
        remaining=remaining,
        period_label='This term',
        resets_or_expires_at=entitlement.ends_at,
        is_term_based=True,
        carry_forward=entitlement.carry_forward,
        purchased_limit=entitlement.purchased_limit,
        entitlement_id=entitlement.id,
        can_carry_on_renewal=(
            plan == QuotaPlan.PRO_PLUS and now < entitlement.ends_at and remaining > 0
        ),
    )


def resolve_quota_state(tenant: Tenant, *, lock: bool = False) -> QuotaState:
    """Return effective quota for a tenant, expiring entitlements when past ends_at."""
    if lock:
        tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
        entitlement = _get_locked_active_entitlement(tenant)
    else:
        entitlement = _active_entitlement_queryset(tenant).first()
        if entitlement and timezone.now() >= entitlement.ends_at:
            with transaction.atomic():
                tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
                entitlement = _get_locked_active_entitlement(tenant)
                if entitlement:
                    return _term_quota_state(tenant, entitlement)
            return _free_quota_state(tenant)

    if entitlement:
        return _term_quota_state(tenant, entitlement)
    return _free_quota_state(tenant)


def _quota_exceeded_message(state: QuotaState) -> str:
    if state.is_free:
        return f'Monthly quota exceeded ({state.limit}/month).'
    return f'Term quota exceeded ({state.limit} until expiry).'


@transaction.atomic
def ensure_quota_remaining(tenant: Tenant) -> QuotaState:
    state = resolve_quota_state(tenant, lock=True)
    if state.remaining <= 0:
        raise QuotaExceededError(_quota_exceeded_message(state))
    return state


@transaction.atomic
def consume_quota(tenant: Tenant) -> QuotaState:
    tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
    entitlement = _get_locked_active_entitlement(tenant)
    if entitlement:
        state = _term_quota_state(tenant, entitlement)
        if state.remaining <= 0:
            raise QuotaExceededError(_quota_exceeded_message(state))
        entitlement.usage_count += 1
        entitlement.save(update_fields=['usage_count', 'updated_at'])
        return _term_quota_state(tenant, entitlement)

    tenant.reset_quota_if_needed()
    state = _free_quota_state(tenant)
    if state.remaining <= 0:
        raise QuotaExceededError(_quota_exceeded_message(state))
    tenant.usage_this_month += 1
    tenant.save(update_fields=['usage_this_month', 'updated_at'])
    return _free_quota_state(tenant)


@transaction.atomic
def grant_entitlement(
    tenant: Tenant,
    *,
    plan: str,
    purchased_limit: int,
    duration_months: int,
    starts_at: datetime | None = None,
    granted_by=None,
    notes: str = '',
) -> QuotaEntitlement:
    if plan not in {QuotaPlan.PRO, QuotaPlan.PRO_PLUS}:
        raise ValueError('plan must be pro or pro_plus')
    if purchased_limit <= 0:
        raise ValueError('purchased_limit must be positive')
    if duration_months <= 0:
        raise ValueError('duration_months must be positive')

    tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
    active = _get_locked_active_entitlement(tenant)
    if active:
        raise ValueError('Tenant already has an active entitlement. Renew instead.')

    starts_at = starts_at or timezone.now()
    ends_at = add_months(starts_at, duration_months)

    entitlement = QuotaEntitlement.objects.create(
        tenant=tenant,
        plan_at_grant=plan,
        purchased_limit=purchased_limit,
        carry_forward=0,
        quota_limit=purchased_limit,
        usage_count=0,
        starts_at=starts_at,
        ends_at=ends_at,
        status=QuotaEntitlementStatus.ACTIVE,
        granted_by=granted_by,
        notes=notes,
    )
    tenant.quota_plan = plan
    tenant.save(update_fields=['quota_plan', 'updated_at'])
    entitlement_id = entitlement.pk
    transaction.on_commit(lambda: _notify_entitlement_granted(entitlement_id))
    return entitlement


@transaction.atomic
def renew_entitlement(
    tenant: Tenant,
    *,
    plan: str,
    purchased_limit: int,
    duration_months: int,
    granted_by=None,
    notes: str = '',
) -> QuotaEntitlement:
    if plan not in {QuotaPlan.PRO, QuotaPlan.PRO_PLUS}:
        raise ValueError('plan must be pro or pro_plus')
    if purchased_limit <= 0:
        raise ValueError('purchased_limit must be positive')
    if duration_months <= 0:
        raise ValueError('duration_months must be positive')

    tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
    current = _get_locked_active_entitlement(tenant)
    now = timezone.now()

    carry_forward = 0
    renewed_from = None
    starts_at = now

    if current and now < current.ends_at:
        renewed_from = current
        if plan == QuotaPlan.PRO_PLUS:
            carry_forward = max(0, current.quota_limit - current.usage_count)
        current.status = QuotaEntitlementStatus.SUPERSEDED
        current.save(update_fields=['status', 'updated_at'])
        starts_at = current.ends_at
    elif current:
        current.status = QuotaEntitlementStatus.EXPIRED
        current.save(update_fields=['status', 'updated_at'])

    ends_at = add_months(starts_at, duration_months)
    entitlement = QuotaEntitlement.objects.create(
        tenant=tenant,
        plan_at_grant=plan,
        purchased_limit=purchased_limit,
        carry_forward=carry_forward,
        quota_limit=purchased_limit + carry_forward,
        usage_count=0,
        starts_at=starts_at,
        ends_at=ends_at,
        status=QuotaEntitlementStatus.ACTIVE,
        renewed_from=renewed_from,
        granted_by=granted_by,
        notes=notes,
    )
    tenant.quota_plan = plan
    tenant.save(update_fields=['quota_plan', 'updated_at'])
    entitlement_id = entitlement.pk
    transaction.on_commit(lambda: _notify_entitlement_renewed(entitlement_id))
    return entitlement


def _notify_entitlement_granted(entitlement_id: int) -> None:
    import logging

    from .quota_notifications import send_entitlement_granted_email

    try:
        send_entitlement_granted_email(entitlement_id)
    except Exception:
        logging.getLogger(__name__).exception(
            'Quota granted email failed for entitlement %s',
            entitlement_id,
        )


def _notify_entitlement_renewed(entitlement_id: int) -> None:
    import logging

    from .quota_notifications import send_entitlement_renewed_email

    try:
        send_entitlement_renewed_email(entitlement_id)
    except Exception:
        logging.getLogger(__name__).exception(
            'Quota renewed email failed for entitlement %s',
            entitlement_id,
        )


def preview_renew_entitlement(
    tenant: Tenant,
    *,
    plan: str,
    purchased_limit: int,
    duration_months: int,
) -> dict:
    """Admin preview for renewal carry-forward and term dates."""
    now = timezone.now()
    current = _active_entitlement_queryset(tenant).first()
    carry_forward = 0
    renewed_before_expiry = False
    starts_at = now
    current_remaining = 0

    if current and now < current.ends_at:
        renewed_before_expiry = True
        current_remaining = max(0, current.quota_limit - current.usage_count)
        if plan == QuotaPlan.PRO_PLUS:
            carry_forward = current_remaining
        starts_at = current.ends_at
    elif current and now >= current.ends_at:
        current_remaining = max(0, current.quota_limit - current.usage_count)

    ends_at = add_months(starts_at, duration_months)
    return {
        'has_current': current is not None,
        'renewed_before_expiry': renewed_before_expiry,
        'current_remaining': current_remaining,
        'carry_forward': carry_forward,
        'purchased_limit': purchased_limit,
        'total_limit': purchased_limit + carry_forward,
        'starts_at': starts_at,
        'ends_at': ends_at,
        'plan': plan,
    }

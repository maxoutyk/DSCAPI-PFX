"""Email notifications to tenant owners for quota entitlements."""

from __future__ import annotations

import logging
import math
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .emailing import EmailDeliveryError, is_smtp_configured
from .models import MembershipRole, QuotaEntitlement, QuotaEntitlementStatus, QuotaPlan, Tenant, TenantMembership
from .templatetags.display_tz import DISPLAY_TZ

logger = logging.getLogger(__name__)


def _notifications_enabled() -> bool:
    return (
        getattr(settings, 'QUOTA_NOTIFICATIONS_ENABLED', True)
        and is_smtp_configured()
    )


def list_tenant_owner_emails(tenant: Tenant) -> list[str]:
    return list(
        TenantMembership.objects.filter(
            tenant=tenant,
            role=MembershipRole.OWNER,
        )
        .order_by('user__email')
        .values_list('user__email', flat=True)
    )


def _plan_label(plan: str) -> str:
    if plan == QuotaPlan.PRO_PLUS:
        return 'Pro+'
    if plan == QuotaPlan.PRO:
        return 'Pro'
    return plan.replace('_', ' ').title()


def _format_dt(value) -> str:
    return timezone.localtime(value, DISPLAY_TZ).strftime('%B %d, %Y')


def _dashboard_url() -> str:
    return f'{settings.SITE_URL.rstrip("/")}/dashboard/'


def _usage_report_url() -> str:
    return f'{settings.SITE_URL.rstrip("/")}/dashboard/usage/'


def _low_quota_threshold(limit: int) -> int:
    percent = getattr(settings, 'QUOTA_LOW_REMAINING_PERCENT', 10)
    return max(1, math.ceil(limit * percent / 100))


def _send_owner_email(*, template_base: str, recipients: list[str], context: dict) -> None:
    if not recipients:
        logger.warning('Skipping quota email %s — no owner recipients', template_base)
        return

    subject = render_to_string(f'accounts/email/{template_base}_subject.txt', context).strip()
    text_body = render_to_string(f'accounts/email/{template_base}.txt', context)
    html_body = render_to_string(f'accounts/email/{template_base}.html', context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    message.attach_alternative(html_body, 'text/html')
    message.send(fail_silently=False)


def _entitlement_context(entitlement: QuotaEntitlement) -> dict:
    return {
        'site_name': 'IG E-Sign',
        'tenant_name': entitlement.tenant.name,
        'plan_label': _plan_label(entitlement.plan_at_grant),
        'quota_limit': entitlement.quota_limit,
        'quota_used': entitlement.usage_count,
        'quota_remaining': entitlement.remaining,
        'starts_at': _format_dt(entitlement.starts_at),
        'ends_at': _format_dt(entitlement.ends_at),
        'carry_forward': entitlement.carry_forward,
        'dashboard_url': _dashboard_url(),
        'usage_report_url': _usage_report_url(),
    }


def send_entitlement_granted_email(entitlement_id: int) -> bool:
    if not _notifications_enabled():
        return False

    entitlement = QuotaEntitlement.objects.select_related('tenant').get(pk=entitlement_id)
    context = _entitlement_context(entitlement)
    try:
        _send_owner_email(
            template_base='quota_entitlement_granted',
            recipients=list_tenant_owner_emails(entitlement.tenant),
            context=context,
        )
    except Exception as exc:
        logger.exception('Failed to send entitlement granted email for %s', entitlement_id)
        raise EmailDeliveryError('Failed to send quota notification email.') from exc
    return True


def send_entitlement_renewed_email(entitlement_id: int) -> bool:
    if not _notifications_enabled():
        return False

    entitlement = (
        QuotaEntitlement.objects.select_related('tenant', 'renewed_from')
        .get(pk=entitlement_id)
    )
    context = _entitlement_context(entitlement)
    if entitlement.renewed_from_id:
        context['previous_remaining'] = entitlement.renewed_from.remaining
    try:
        _send_owner_email(
            template_base='quota_entitlement_renewed',
            recipients=list_tenant_owner_emails(entitlement.tenant),
            context=context,
        )
    except Exception as exc:
        logger.exception('Failed to send entitlement renewed email for %s', entitlement_id)
        raise EmailDeliveryError('Failed to send quota notification email.') from exc
    return True


@transaction.atomic
def send_expiry_reminder_email(entitlement: QuotaEntitlement) -> bool:
    if not _notifications_enabled():
        return False

    entitlement = (
        QuotaEntitlement.objects.select_for_update()
        .select_related('tenant')
        .get(pk=entitlement.pk)
    )
    if entitlement.expiry_reminder_sent_at is not None:
        return False
    if entitlement.status != QuotaEntitlementStatus.ACTIVE:
        return False

    now = timezone.now()
    reminder_days = getattr(settings, 'QUOTA_EXPIRY_REMINDER_DAYS', 30)
    if now >= entitlement.ends_at or entitlement.ends_at - now > timedelta(days=reminder_days):
        return False

    days_remaining = max(0, (entitlement.ends_at - now).days)
    context = _entitlement_context(entitlement)
    context['days_remaining'] = days_remaining
    context['reminder_days'] = reminder_days

    try:
        _send_owner_email(
            template_base='quota_expiry_reminder',
            recipients=list_tenant_owner_emails(entitlement.tenant),
            context=context,
        )
    except Exception as exc:
        logger.exception('Failed to send expiry reminder for entitlement %s', entitlement.pk)
        raise EmailDeliveryError('Failed to send quota notification email.') from exc

    entitlement.expiry_reminder_sent_at = timezone.now()
    entitlement.save(update_fields=['expiry_reminder_sent_at', 'updated_at'])
    return True


@transaction.atomic
def send_low_quota_email(entitlement: QuotaEntitlement) -> bool:
    if not _notifications_enabled():
        return False

    entitlement = (
        QuotaEntitlement.objects.select_for_update()
        .select_related('tenant')
        .get(pk=entitlement.pk)
    )
    if entitlement.low_quota_notified_at is not None:
        return False
    if entitlement.status != QuotaEntitlementStatus.ACTIVE:
        return False

    threshold = _low_quota_threshold(entitlement.quota_limit)
    if entitlement.remaining > threshold:
        return False

    context = _entitlement_context(entitlement)
    context['low_quota_threshold'] = threshold
    context['quota_exhausted'] = entitlement.remaining <= 0

    try:
        _send_owner_email(
            template_base='quota_low_remaining',
            recipients=list_tenant_owner_emails(entitlement.tenant),
            context=context,
        )
    except Exception as exc:
        logger.exception('Failed to send low quota email for entitlement %s', entitlement.pk)
        raise EmailDeliveryError('Failed to send quota notification email.') from exc

    entitlement.low_quota_notified_at = timezone.now()
    entitlement.save(update_fields=['low_quota_notified_at', 'updated_at'])
    return True


def process_scheduled_quota_notifications() -> dict:
    """Send expiry reminders and low-quota alerts for active entitlements."""
    if not _notifications_enabled():
        return {'expiry_reminders': 0, 'low_quota': 0, 'skipped': 'notifications_disabled'}

    now = timezone.now()
    reminder_days = getattr(settings, 'QUOTA_EXPIRY_REMINDER_DAYS', 30)
    reminder_cutoff = now + timedelta(days=reminder_days)

    expiry_sent = 0
    low_sent = 0

    active = QuotaEntitlement.objects.filter(
        status=QuotaEntitlementStatus.ACTIVE,
        ends_at__gt=now,
    ).select_related('tenant')

    for entitlement in active:
        if (
            entitlement.expiry_reminder_sent_at is None
            and entitlement.ends_at <= reminder_cutoff
        ):
            try:
                if send_expiry_reminder_email(entitlement):
                    expiry_sent += 1
            except EmailDeliveryError:
                logger.warning('Expiry reminder failed for entitlement %s', entitlement.pk)

        threshold = _low_quota_threshold(entitlement.quota_limit)
        if (
            entitlement.low_quota_notified_at is None
            and entitlement.remaining <= threshold
        ):
            try:
                if send_low_quota_email(entitlement):
                    low_sent += 1
            except EmailDeliveryError:
                logger.warning('Low quota email failed for entitlement %s', entitlement.pk)

    return {'expiry_reminders': expiry_sent, 'low_quota': low_sent}

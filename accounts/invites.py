"""Team invite creation and acceptance."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import MembershipRole, Tenant, TenantInvite, TenantMembership
from .services import user_is_tenant_owner


class InviteError(Exception):
    pass


def normalize_invite_email(email: str) -> str:
    return email.strip().lower()


def list_pending_invites(tenant: Tenant):
    now = timezone.now()
    return (
        TenantInvite.objects.filter(
            tenant=tenant,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=now,
        )
        .select_related('invited_by')
        .order_by('-created_at')
    )


def get_invite_by_token(token) -> TenantInvite | None:
    return (
        TenantInvite.objects.select_related('tenant', 'invited_by')
        .filter(token=token)
        .first()
    )


def _user_owns_other_tenant(user: User, *, excluding_tenant: Tenant | None = None) -> bool:
    qs = TenantMembership.objects.filter(user=user, role=MembershipRole.OWNER)
    if excluding_tenant is not None:
        qs = qs.exclude(tenant=excluding_tenant)
    return qs.exists()


def _user_has_other_membership(user: User, *, excluding_tenant: Tenant) -> bool:
    return TenantMembership.objects.filter(user=user).exclude(tenant=excluding_tenant).exists()


def _invite_expiry():
    return timezone.now() + timedelta(hours=settings.TEAM_INVITE_HOURS)


@transaction.atomic
def create_tenant_invite(*, tenant: Tenant, email: str, invited_by) -> TenantInvite:
    if not settings.TEAMS_ENABLED:
        raise InviteError('Team invites are not enabled on this environment.')

    if not user_is_tenant_owner(invited_by):
        raise InviteError('Only organization owners can invite team members.')

    normalized = normalize_invite_email(email)
    if not normalized:
        raise InviteError('Enter a valid email address.')

    if TenantMembership.objects.filter(tenant=tenant, user__email__iexact=normalized).exists():
        raise InviteError('This person is already a member of your organization.')

    existing_user = User.objects.filter(email__iexact=normalized).first()
    if existing_user and _user_owns_other_tenant(existing_user, excluding_tenant=tenant):
        raise InviteError(
            'This email already owns another organization. '
            'Ask them to use a different email or contact support.',
        )

    expires_at = _invite_expiry()
    pending = (
        TenantInvite.objects.select_for_update()
        .filter(
            tenant=tenant,
            email=normalized,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        )
        .first()
    )
    if pending is not None:
        pending.token = uuid.uuid4()
        pending.expires_at = expires_at
        pending.invited_by = invited_by
        pending.save(update_fields=['token', 'expires_at', 'invited_by'])
        invite = pending
    else:
        invite = TenantInvite.objects.create(
            tenant=tenant,
            email=normalized,
            role=MembershipRole.MEMBER,
            invited_by=invited_by,
            expires_at=expires_at,
        )

    from .emailing import send_team_invite_email

    send_team_invite_email(invite)
    return invite


@transaction.atomic
def register_invite_user(*, email: str, password: str) -> User:
    normalized = normalize_invite_email(email)
    if User.objects.filter(email__iexact=normalized).exists():
        raise InviteError('An account with this email already exists. Sign in instead.')

    return User.objects.create_user(
        username=normalized,
        email=normalized,
        password=password,
        is_active=True,
    )


@transaction.atomic
def accept_tenant_invite(*, invite: TenantInvite, user: User) -> Tenant:
    if not settings.TEAMS_ENABLED:
        raise InviteError('Team invites are not enabled on this environment.')

    invite = (
        TenantInvite.objects.select_for_update()
        .select_related('tenant')
        .get(pk=invite.pk)
    )

    if invite.revoked_at is not None:
        raise InviteError('This invite has been revoked. Ask the owner to send a new invite.')

    if invite.accepted_at is not None:
        if TenantMembership.objects.filter(tenant=invite.tenant, user=user).exists():
            return invite.tenant
        raise InviteError('This invite has already been used.')

    if timezone.now() > invite.expires_at:
        raise InviteError('This invite has expired. Ask the owner to send a new invite.')

    if normalize_invite_email(user.email) != invite.email:
        raise InviteError('Sign in with the email address that received the invite.')

    if _user_owns_other_tenant(user, excluding_tenant=invite.tenant):
        raise InviteError(
            'You already have an organization. Contact support to transfer or use a different email.',
        )

    if _user_has_other_membership(user, excluding_tenant=invite.tenant):
        raise InviteError(
            'This account is already linked to another organization. '
            'Contact support if you need access moved.',
        )

    membership = TenantMembership.objects.filter(tenant=invite.tenant, user=user).first()
    if membership is None:
        TenantMembership.objects.create(
            tenant=invite.tenant,
            user=user,
            role=MembershipRole.MEMBER,
            is_primary=True,
        )
    elif membership.role != MembershipRole.MEMBER:
        pass

    invite.accepted_at = timezone.now()
    invite.save(update_fields=['accepted_at'])
    return invite.tenant


def _get_pending_invite(*, tenant: Tenant, invite_id) -> TenantInvite:
    invite = (
        TenantInvite.objects.select_for_update()
        .filter(pk=invite_id, tenant=tenant)
        .first()
    )
    if invite is None:
        raise InviteError('Invite not found.')
    if invite.accepted_at is not None:
        raise InviteError('This invite was already accepted.')
    if invite.revoked_at is not None:
        raise InviteError('This invite was revoked.')
    return invite


@transaction.atomic
def resend_tenant_invite(*, tenant: Tenant, invite_id, acting_user) -> TenantInvite:
    if not settings.TEAMS_ENABLED:
        raise InviteError('Team invites are not enabled on this environment.')

    if not user_is_tenant_owner(acting_user):
        raise InviteError('Only organization owners can resend team invites.')

    invite = _get_pending_invite(tenant=tenant, invite_id=invite_id)
    invite.token = uuid.uuid4()
    invite.expires_at = _invite_expiry()
    invite.invited_by = acting_user
    invite.save(update_fields=['token', 'expires_at', 'invited_by'])

    from .emailing import send_team_invite_email

    send_team_invite_email(invite)
    return invite


@transaction.atomic
def revoke_tenant_invite(*, tenant: Tenant, invite_id, acting_user) -> str:
    if not settings.TEAMS_ENABLED:
        raise InviteError('Team invites are not enabled on this environment.')

    if not user_is_tenant_owner(acting_user):
        raise InviteError('Only organization owners can revoke team invites.')

    invite = _get_pending_invite(tenant=tenant, invite_id=invite_id)
    invite.revoked_at = timezone.now()
    invite.save(update_fields=['revoked_at'])
    return invite.email

"""Team membership helpers for portal organization management."""

from __future__ import annotations

from django.db import transaction

from .models import MembershipRole, Tenant, TenantMembership
from .services import user_is_tenant_owner


class TeamError(Exception):
    pass


def list_tenant_memberships(tenant: Tenant):
    return (
        TenantMembership.objects.filter(tenant=tenant)
        .select_related('user')
        .order_by('role', 'user__email')
    )


def count_tenant_owners(tenant: Tenant) -> int:
    return TenantMembership.objects.filter(tenant=tenant, role=MembershipRole.OWNER).count()


@transaction.atomic
def remove_tenant_member(*, tenant: Tenant, membership_id: int, acting_user) -> str:
    if not user_is_tenant_owner(acting_user):
        raise TeamError('Only organization owners can remove team members.')

    membership = (
        TenantMembership.objects.select_for_update()
        .filter(pk=membership_id, tenant=tenant)
        .select_related('user')
        .first()
    )
    if membership is None:
        raise TeamError('Team member not found.')

    if membership.role == MembershipRole.OWNER and count_tenant_owners(tenant) <= 1:
        raise TeamError('You cannot remove the last organization owner.')

    user_email = membership.user.email
    membership.delete()
    return user_email

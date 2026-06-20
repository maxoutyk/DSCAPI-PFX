from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import QuotaEntitlementStatus, QuotaPlan, Tenant, TenantStatus
from accounts.quota import (
    QuotaExceededError,
    consume_quota,
    grant_entitlement,
    renew_entitlement,
    resolve_quota_state,
)
from accounts.services import record_signing_event


class FreeQuotaTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Free Org',
            slug='free-org',
            status=TenantStatus.ACTIVE,
            quota_plan=QuotaPlan.FREE,
            monthly_quota=100,
            usage_this_month=40,
        )

    def test_free_quota_remaining(self):
        state = resolve_quota_state(self.tenant)
        self.assertEqual(state.plan, QuotaPlan.FREE)
        self.assertEqual(state.limit, 100)
        self.assertEqual(state.used, 40)
        self.assertEqual(state.remaining, 60)
        self.assertFalse(state.is_term_based)

    def test_free_monthly_reset(self):
        self.tenant.quota_reset_at = timezone.now() - timedelta(days=1)
        self.tenant.save(update_fields=['quota_reset_at'])
        state = resolve_quota_state(self.tenant)
        self.tenant.refresh_from_db()
        self.assertEqual(state.used, 0)
        self.assertEqual(self.tenant.usage_this_month, 0)

    def test_consume_quota_increments_free_usage(self):
        consume_quota(self.tenant)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.usage_this_month, 41)

    def test_record_signing_event_uses_free_quota(self):
        record_signing_event(self.tenant, success=True)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.usage_this_month, 41)


class ProQuotaTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Pro Org',
            slug='pro-org',
            status=TenantStatus.ACTIVE,
            quota_plan=QuotaPlan.PRO,
            monthly_quota=100,
        )

    def test_pro_term_does_not_reset_monthly_usage_counter(self):
        grant_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO,
            purchased_limit=20_000,
            duration_months=3,
        )
        entitlement = self.tenant.quota_entitlements.get(status=QuotaEntitlementStatus.ACTIVE)
        entitlement.usage_count = 5_000
        entitlement.save(update_fields=['usage_count'])

        self.tenant.usage_this_month = 99
        self.tenant.quota_reset_at = timezone.now() - timedelta(days=1)
        self.tenant.save(update_fields=['usage_this_month', 'quota_reset_at'])

        state = resolve_quota_state(self.tenant)
        self.assertEqual(state.plan, QuotaPlan.PRO)
        self.assertEqual(state.used, 5_000)
        self.assertEqual(state.remaining, 15_000)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.usage_this_month, 99)

    def test_pro_consume_updates_entitlement_not_monthly_counter(self):
        grant_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO,
            purchased_limit=100,
            duration_months=3,
        )
        consume_quota(self.tenant)
        entitlement = self.tenant.quota_entitlements.get(status=QuotaEntitlementStatus.ACTIVE)
        self.assertEqual(entitlement.usage_count, 1)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.usage_this_month, 0)

    def test_pro_expiry_falls_back_to_free(self):
        grant_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO,
            purchased_limit=20_000,
            duration_months=1,
        )
        entitlement = self.tenant.quota_entitlements.get(status=QuotaEntitlementStatus.ACTIVE)
        entitlement.ends_at = timezone.now() - timedelta(hours=1)
        entitlement.save(update_fields=['ends_at'])

        state = resolve_quota_state(self.tenant)
        self.tenant.refresh_from_db()
        entitlement.refresh_from_db()

        self.assertEqual(state.plan, QuotaPlan.FREE)
        self.assertEqual(state.limit, 100)
        self.assertEqual(entitlement.status, QuotaEntitlementStatus.EXPIRED)
        self.assertEqual(self.tenant.quota_plan, QuotaPlan.FREE)

    def test_pro_renew_before_expiry_no_carry(self):
        grant_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO,
            purchased_limit=20_000,
            duration_months=3,
        )
        entitlement = self.tenant.quota_entitlements.get(status=QuotaEntitlementStatus.ACTIVE)
        entitlement.usage_count = 13_000
        entitlement.save(update_fields=['usage_count'])

        renewed = renew_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO,
            purchased_limit=20_000,
            duration_months=3,
        )
        entitlement.refresh_from_db()

        self.assertEqual(entitlement.status, QuotaEntitlementStatus.SUPERSEDED)
        self.assertEqual(renewed.carry_forward, 0)
        self.assertEqual(renewed.quota_limit, 20_000)
        self.assertEqual(renewed.usage_count, 0)


class ProPlusQuotaTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Pro Plus Org',
            slug='pro-plus-org',
            status=TenantStatus.ACTIVE,
            quota_plan=QuotaPlan.PRO_PLUS,
            monthly_quota=100,
        )

    def test_pro_plus_renew_before_expiry_carries_unused(self):
        grant_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO_PLUS,
            purchased_limit=20_000,
            duration_months=3,
        )
        entitlement = self.tenant.quota_entitlements.get(status=QuotaEntitlementStatus.ACTIVE)
        entitlement.usage_count = 13_000
        entitlement.save(update_fields=['usage_count'])

        renewed = renew_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO_PLUS,
            purchased_limit=20_000,
            duration_months=3,
        )

        self.assertEqual(renewed.carry_forward, 7_000)
        self.assertEqual(renewed.quota_limit, 27_000)
        state = resolve_quota_state(self.tenant)
        self.assertTrue(state.can_carry_on_renewal)

    def test_pro_plus_late_renewal_no_carry(self):
        grant_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO_PLUS,
            purchased_limit=20_000,
            duration_months=1,
        )
        entitlement = self.tenant.quota_entitlements.get(status=QuotaEntitlementStatus.ACTIVE)
        entitlement.usage_count = 13_000
        entitlement.ends_at = timezone.now() - timedelta(hours=1)
        entitlement.save(update_fields=['usage_count', 'ends_at'])

        renewed = renew_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO_PLUS,
            purchased_limit=20_000,
            duration_months=3,
        )

        self.assertEqual(renewed.carry_forward, 0)
        self.assertEqual(renewed.quota_limit, 20_000)

    def test_pro_plus_quota_exceeded(self):
        grant_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO_PLUS,
            purchased_limit=2,
            duration_months=3,
        )
        consume_quota(self.tenant)
        consume_quota(self.tenant)
        with self.assertRaises(QuotaExceededError):
            consume_quota(self.tenant)


class ExistingUserCompatibilityTests(TestCase):
    def test_legacy_tenant_defaults_to_free_monthly(self):
        tenant = Tenant.objects.create(
            name='Legacy Org',
            slug='legacy-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=250,
            usage_this_month=10,
        )
        self.assertEqual(tenant.quota_plan, QuotaPlan.FREE)
        state = resolve_quota_state(tenant)
        self.assertEqual(state.limit, 250)
        self.assertEqual(state.used, 10)

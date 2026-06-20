from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import APIKey, QuotaEntitlementStatus, QuotaPlan, Tenant, TenantStatus
from accounts.quota import grant_entitlement


class TenantAdminQuotaWizardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='admin-pass-123',
        )
        self.tenant = Tenant.objects.create(
            name='Wizard Org',
            slug='wizard-org',
            status=TenantStatus.ACTIVE,
            quota_plan=QuotaPlan.FREE,
            monthly_quota=100,
        )
        self.client = Client()
        self.client.force_login(self.admin)

    def test_grant_quota_wizard_creates_entitlement(self):
        url = reverse('admin:accounts_tenant_grant_quota', args=[self.tenant.pk])
        response = self.client.post(url, {
            'plan': QuotaPlan.PRO,
            'purchased_limit': 20_000,
            'duration_months': 3,
            'notes': 'Invoice #1001',
        })
        self.assertEqual(response.status_code, 302)
        entitlement = self.tenant.quota_entitlements.get(status=QuotaEntitlementStatus.ACTIVE)
        self.assertEqual(entitlement.purchased_limit, 20_000)
        self.assertEqual(entitlement.quota_limit, 20_000)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.quota_plan, QuotaPlan.PRO)

    def test_grant_quota_blocked_when_active_exists(self):
        grant_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO,
            purchased_limit=5_000,
            duration_months=1,
        )
        url = reverse('admin:accounts_tenant_grant_quota', args=[self.tenant.pk])
        response = self.client.post(url, {
            'plan': QuotaPlan.PRO,
            'purchased_limit': 20_000,
            'duration_months': 3,
            'notes': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.tenant.quota_entitlements.filter(status=QuotaEntitlementStatus.ACTIVE).count(),
            1,
        )

    def test_renew_quota_wizard_pro_plus_carry(self):
        grant_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO_PLUS,
            purchased_limit=20_000,
            duration_months=3,
        )
        entitlement = self.tenant.quota_entitlements.get(status=QuotaEntitlementStatus.ACTIVE)
        entitlement.usage_count = 13_000
        entitlement.save(update_fields=['usage_count'])

        url = reverse('admin:accounts_tenant_renew_quota', args=[self.tenant.pk])
        response = self.client.post(url, {
            'plan': QuotaPlan.PRO_PLUS,
            'purchased_limit': 20_000,
            'duration_months': 3,
            'notes': 'Renewal',
        })
        self.assertEqual(response.status_code, 302)
        renewed = self.tenant.quota_entitlements.get(status=QuotaEntitlementStatus.ACTIVE)
        self.assertEqual(renewed.carry_forward, 7_000)
        self.assertEqual(renewed.quota_limit, 27_000)

    def test_renew_preview_does_not_create_entitlement(self):
        grant_entitlement(
            self.tenant,
            plan=QuotaPlan.PRO,
            purchased_limit=10_000,
            duration_months=2,
        )
        url = reverse('admin:accounts_tenant_renew_quota', args=[self.tenant.pk])
        response = self.client.post(url, {
            'plan': QuotaPlan.PRO,
            'purchased_limit': 20_000,
            'duration_months': 3,
            'notes': '',
            '_preview': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Renewal preview')
        self.assertEqual(
            self.tenant.quota_entitlements.filter(status=QuotaEntitlementStatus.ACTIVE).count(),
            1,
        )


class APIKeyAdminRevokeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin2@example.com',
            email='admin2@example.com',
            password='admin-pass-123',
        )
        self.tenant = Tenant.objects.create(
            name='Keys Org',
            slug='keys-org',
            status=TenantStatus.ACTIVE,
        )
        self.api_key = APIKey.objects.create(
            tenant=self.tenant,
            name='Prod',
            prefix='dsc_live_test12',
            key_hash='abc',
        )
        self.client = Client()
        self.client.force_login(self.admin)

    def test_revoke_api_keys_action(self):
        url = reverse('admin:accounts_apikey_changelist')
        response = self.client.post(url, {
            'action': 'revoke_api_keys',
            '_selected_action': [str(self.api_key.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.api_key.refresh_from_db()
        self.assertIsNotNone(self.api_key.revoked_at)

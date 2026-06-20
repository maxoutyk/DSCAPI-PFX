from datetime import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Tenant, TenantStatus, UsageLog
from accounts.services import create_api_key
from accounts.templatetags.display_tz import DISPLAY_TZ


class UsageReportApiTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme',
            slug='acme-usage-api',
            status=TenantStatus.ACTIVE,
            quota_reset_at='2099-01-01T00:00:00Z',
        )
        self.key_a, self.full_key_a = create_api_key(self.tenant, 'Key A', customer_label='Customer A')
        self.key_b, self.full_key_b = create_api_key(self.tenant, 'Key B', customer_label='Customer B')
        self.client = APIClient()

        may_time = timezone.make_aware(datetime(2026, 5, 15, 12, 0, 0), DISPLAY_TZ)
        log = UsageLog.objects.create(tenant=self.tenant, api_key=self.key_a, success=True)
        UsageLog.objects.filter(pk=log.pk).update(created_at=may_time)

    def _auth(self, full_key):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {full_key}')

    def test_requires_api_key(self):
        response = self.client.get('/api/usage/report/')
        self.assertEqual(response.status_code, 403)

    def test_overall_pdf_download(self):
        self._auth(self.full_key_b)
        response = self.client.get('/api/usage/report/?scope=overall&export=pdf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertIn('attachment', response['Content-Disposition'])

    def test_customer_report_by_label(self):
        self._auth(self.full_key_b)
        response = self.client.get(
            '/api/usage/report/?scope=customer&customer=Customer%20A&export=json&period=2026-05',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['customer']['label'], 'Customer A')
        self.assertEqual(response.json()['total_usage'], 1)

    def test_auto_scopes_to_api_key_customer_label(self):
        self._auth(self.full_key_a)
        response = self.client.get('/api/usage/report/?export=json&period=2026-05')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['scope'], 'customer')
        self.assertEqual(body['customer']['label'], 'Customer A')

    def test_customer_not_found(self):
        self._auth(self.full_key_b)
        response = self.client.get('/api/usage/report/?scope=customer&customer=Missing&export=json')
        self.assertEqual(response.status_code, 404)

    def test_inactive_tenant_rejected(self):
        self.tenant.status = TenantStatus.SUSPENDED
        self.tenant.save(update_fields=['status'])
        self._auth(self.full_key_a)
        response = self.client.get('/api/usage/report/?export=json')
        self.assertEqual(response.status_code, 403)

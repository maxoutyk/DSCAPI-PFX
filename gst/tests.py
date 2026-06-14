from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import CompanyProfile, Tenant, TenantMembership, TenantStatus
from accounts.services import create_api_key, get_company_profile


def _complete_profile(tenant: Tenant) -> CompanyProfile:
    profile = get_company_profile(tenant)
    profile.company_name = 'Acme Pvt Ltd'
    profile.gstin = '33AAUPP8709M3ZS'
    profile.pan = 'AAUPP8709M'
    profile.address = '123 MG Road'
    profile.city = 'Chennai'
    profile.state = '33'
    profile.pincode = '600001'
    profile.primary_email = 'owner@acme.test'
    profile.primary_name = 'Owner Name'
    profile.primary_mobile = '9876543210'
    profile.save()
    return profile


@override_settings(
    GST_MYGSTCAFE_CUSTOMER_ID='cust-1',
    GST_MYGSTCAFE_API_ID='api-1',
    GST_MYGSTCAFE_API_SECRET='secret-1',
    GST_MYGSTCAFE_ENVIRONMENT='Sandbox',
    GST_PARTNER_BASE_URL='https://gstapi.mygstcafe.com',
)
class GstLookupApiTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme',
            slug='acme',
            status=TenantStatus.ACTIVE,
            quota_reset_at='2099-01-01T00:00:00Z',
        )
        self.user = User.objects.create_user(
            username='owner@acme.test',
            email='owner@acme.test',
            password='testpass123',
        )
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role='owner', is_primary=True)
        _api_key, self.raw_key = create_api_key(self.tenant, 'Test')
        self.client = APIClient()

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.raw_key}')

    def test_requires_complete_profile(self):
        self._auth()
        response = self.client.get('/api/gst/gstin/search/')
        self.assertEqual(response.status_code, 403)
        self.assertIn('profile', response.json()['error'].lower())

    @patch('gst.lookup_handlers.MyGSTCafeLookupClient.get_gstin_details')
    def test_gstin_search_success(self, mock_lookup):
        _complete_profile(self.tenant)
        mock_lookup.return_value = {'status': 'ok', 'tradeName': 'Acme'}
        self._auth()
        response = self.client.get('/api/gst/gstin/search/')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['gstin'], '33AAUPP8709M3ZS')
        self.assertEqual(body['data']['tradeName'], 'Acme')
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.gst_usage_this_month, 1)

    @patch('gst.lookup_handlers.MyGSTCafeLookupClient.get_gstin_details')
    def test_accepts_any_valid_gstin(self, mock_lookup):
        _complete_profile(self.tenant)
        mock_lookup.return_value = {'status': 'ok', 'tradeName': 'Other Co'}
        self._auth()
        response = self.client.get('/api/gst/gstin/search/?gstin=27AAAAA0000A1Z5')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['gstin'], '27AAAAA0000A1Z5')
        mock_lookup.assert_called_once_with('27AAAAA0000A1Z5')

    @patch('gst.lookup_handlers.MyGSTCafeLookupClient.get_gstin_details')
    def test_rejects_when_quota_exhausted_before_partner(self, mock_lookup):
        _complete_profile(self.tenant)
        self.tenant.gst_monthly_quota = 1
        self.tenant.gst_usage_this_month = 1
        self.tenant.save(update_fields=['gst_monthly_quota', 'gst_usage_this_month'])
        self._auth()
        response = self.client.get('/api/gst/gstin/search/')
        self.assertEqual(response.status_code, 429)
        mock_lookup.assert_not_called()

    @patch('gst.lookup_handlers.get_client_ip', return_value=None)
    @patch('gst.lookup_handlers.MyGSTCafeLookupClient.get_return_status')
    def test_return_status_requires_client_ip(self, mock_lookup, _mock_ip):
        _complete_profile(self.tenant)
        self._auth()
        response = self.client.get('/api/gst/returns/?fy=2024-25')
        self.assertEqual(response.status_code, 400)
        mock_lookup.assert_not_called()

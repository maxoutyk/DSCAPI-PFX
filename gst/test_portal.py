from unittest.mock import patch



from django.contrib.auth.models import User

from django.test import Client, TestCase, override_settings



from accounts.models import MembershipRole, Tenant, TenantMembership, TenantStatus

from accounts.services import get_company_profile



from .tests import _complete_profile





def _portal_post(client, **data):

    return client.post('/dashboard/gst/try/', data)





@override_settings(

    GST_MYGSTCAFE_CUSTOMER_ID='cust-1',

    GST_MYGSTCAFE_API_ID='api-1',

    GST_MYGSTCAFE_API_SECRET='secret-1',

    GST_MYGSTCAFE_ENVIRONMENT='Sandbox',

    GST_PARTNER_BASE_URL='https://gstapi.mygstcafe.com',

)

class GstPortalDashboardTests(TestCase):

    def setUp(self):

        self.tenant = Tenant.objects.create(

            name='Acme',

            slug='acme-portal',

            status=TenantStatus.ACTIVE,

            quota_reset_at='2099-01-01T00:00:00Z',

        )

        self.user = User.objects.create_user(

            username='portal@acme.test',

            email='portal@acme.test',

            password='testpass123',

        )

        TenantMembership.objects.create(

            tenant=self.tenant,

            user=self.user,

            role='owner',

            is_primary=True,

        )

        self.client = Client()

        self.client.login(username='portal@acme.test', password='testpass123')



    def test_gst_dashboard_renders_request_console(self):

        response = self.client.get('/dashboard/gst/')

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'gst-console')

        self.assertContains(response, 'gst-console-tabs')

        self.assertContains(response, 'GSTIN details')

        self.assertContains(response, 'Filing preferences')

        self.assertContains(response, 'Return status')

        self.assertContains(response, 'Look up GSTIN')

        self.assertContains(response, 'gst-gstin-search')

        self.assertContains(response, 'gst-preference')

        self.assertContains(response, 'gst-return-status')

        self.assertNotContains(response, 'api-docs.js')

        self.assertNotContains(response, 'gst-portal-data')

        self.assertNotContains(response, 'mygstcafe')



    def test_portal_try_rejects_get(self):

        _complete_profile(self.tenant)

        response = self.client.get('/dashboard/gst/try/?endpoint=gst-gstin-search')

        self.assertEqual(response.status_code, 405)



    def test_portal_try_requires_profile(self):

        response = _portal_post(self.client, endpoint='gst-gstin-search')

        self.assertEqual(response.status_code, 403)

        self.assertIn('profile', response.json()['error'].lower())



    @patch('gst.lookup_handlers.MyGSTCafeLookupClient.get_gstin_details')

    def test_portal_try_executes_gstin_search(self, mock_lookup):

        _complete_profile(self.tenant)

        mock_lookup.return_value = {'tradeName': 'Acme'}

        response = _portal_post(self.client, endpoint='gst-gstin-search')

        self.assertEqual(response.status_code, 200)

        body = response.json()

        self.assertEqual(body['gstin'], get_company_profile(self.tenant).gstin)

        self.assertEqual(body['data']['tradeName'], 'Acme')

        self.assertIn('X-GST-Quota-Remaining', response)



    @patch('gst.lookup_handlers.MyGSTCafeLookupClient.get_gstin_details')

    def test_portal_try_accepts_other_gstin(self, mock_lookup):

        _complete_profile(self.tenant)

        mock_lookup.return_value = {'tradeName': 'Vendor Co'}

        response = _portal_post(self.client, endpoint='gst-gstin-search', gstin='27AAAAA0000A1Z5')

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.json()['gstin'], '27AAAAA0000A1Z5')

        mock_lookup.assert_called_once_with('27AAAAA0000A1Z5')



    def test_portal_try_rejects_unknown_endpoint(self):

        _complete_profile(self.tenant)

        response = _portal_post(self.client, endpoint='unknown')

        self.assertEqual(response.status_code, 400)



    def test_portal_try_rejects_non_owner(self):

        _complete_profile(self.tenant)

        member = User.objects.create_user(

            username='member@acme.test',

            email='member@acme.test',

            password='testpass123',

        )

        TenantMembership.objects.create(

            tenant=self.tenant,

            user=member,

            role=MembershipRole.MEMBER,

            is_primary=True,

        )

        self.client.logout()

        self.client.login(username='member@acme.test', password='testpass123')

        response = _portal_post(self.client, endpoint='gst-gstin-search')

        self.assertEqual(response.status_code, 403)

        self.assertIn('owner', response.json()['error'].lower())



    @patch('gst.lookup_handlers.MyGSTCafeLookupClient.get_gstin_details')

    def test_portal_try_checks_quota_before_partner(self, mock_lookup):

        _complete_profile(self.tenant)

        self.tenant.gst_monthly_quota = 1

        self.tenant.gst_usage_this_month = 1

        self.tenant.save(update_fields=['gst_monthly_quota', 'gst_usage_this_month'])

        response = _portal_post(self.client, endpoint='gst-gstin-search')

        self.assertEqual(response.status_code, 429)

        mock_lookup.assert_not_called()


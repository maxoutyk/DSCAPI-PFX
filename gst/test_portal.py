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



    def test_gst_dashboard_redirects_to_first_service(self):

        _complete_profile(self.tenant)

        response = self.client.get('/dashboard/gst/')

        self.assertEqual(response.status_code, 302)

        self.assertEqual(response.url, '/dashboard/gst/gst-gstin-search/')



    def test_gst_dashboard_renders_request_console(self):

        _complete_profile(self.tenant)

        response = self.client.get('/dashboard/gst/gst-gstin-search/')

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'gst-console')

        self.assertNotContains(response, 'gst-console-tabs')

        self.assertContains(response, 'GSTIN details')

        self.assertContains(response, 'Filing preferences')

        self.assertContains(response, 'Return status')

        self.assertContains(response, 'E-WAY bill')

        self.assertContains(response, 'E-invoice IRN')

        self.assertContains(response, 'Look up GSTIN')

        self.assertContains(response, 'gst-network-badge')

        self.assertContains(response, 'GST network connected')

        self.assertNotContains(response, 'Requests remaining')

        self.assertNotContains(response, 'name="nicUsername"')

        self.assertNotContains(response, 'name="nicPassword"')

        self.assertNotContains(response, 'kpi-grid')

        self.assertContains(response, '/dashboard/gst/gst-preference/')

        self.assertContains(response, '/dashboard/gst/gst-return-status/')

        self.assertContains(response, 'gst-eway-print')

        self.assertContains(response, 'gst-irn-print')

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

        self.assertIn('X-Quota-Remaining', response)



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

        self.tenant.monthly_quota = 1

        self.tenant.usage_this_month = 1

        self.tenant.save(update_fields=['monthly_quota', 'usage_this_month'])

        response = _portal_post(self.client, endpoint='gst-gstin-search')

        self.assertEqual(response.status_code, 429)

        mock_lookup.assert_not_called()



    @patch('gst.lookup_handlers.MyGSTCafePrintClient.get_eway_detailed_print')

    def test_portal_try_executes_eway_print(self, mock_print):

        _complete_profile(self.tenant)

        page = self.client.get('/dashboard/gst/gst-eway-print/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'id="gst-gst-eway-print-ewbNumber"')
        self.assertNotContains(page, 'id="gst-gst-eway-print-gstin"')
        self.assertNotContains(page, 'name="nicUsername"')
        self.assertNotContains(page, 'name="nicPassword"')

        mock_print.return_value = b'%PDF-1.4 eway'

        response = _portal_post(self.client, endpoint='gst-eway-print', ewbNumber='123456789012')

        self.assertEqual(response.status_code, 200)

        body = response.json()

        self.assertEqual(body['ewb_number'], '123456789012')

        self.assertIn('pdf_base64', body)

        mock_print.assert_called_once_with(
            '123456789012',
            get_company_profile(self.tenant).gstin,
            nic_username='nic_user',
            nic_password='nic_secret',
        )



    @patch('gst.lookup_handlers.MyGSTCafePrintClient.get_einvoice_pdf')

    def test_portal_try_executes_irn_print(self, mock_print):

        _complete_profile(self.tenant)

        irn = '2d4cacc69309dcb5b07c064ba6f88237d3eab6f171e3e95da8d91a0e93702c2f'

        mock_print.return_value = b'%PDF-1.4 irn'

        response = _portal_post(self.client, endpoint='gst-irn-print', irn=irn)

        self.assertEqual(response.status_code, 200)

        body = response.json()

        self.assertEqual(body['irn'], irn)

        self.assertIn('pdf_base64', body)

        mock_print.assert_called_once_with(
            irn,
            get_company_profile(self.tenant).gstin,
            nic_username='nic_user',
            nic_password='nic_secret',
        )

    @patch('gst.lookup_handlers.MyGSTCafePrintClient.get_eway_detailed_print')
    def test_portal_try_ignores_api_nic_overrides(self, mock_print):
        _complete_profile(self.tenant)
        profile = get_company_profile(self.tenant)
        profile.encrypted_nic_portal_password = None
        profile.nic_portal_username = ''
        profile.save(update_fields=['encrypted_nic_portal_password', 'nic_portal_username', 'updated_at'])
        response = _portal_post(
            self.client,
            endpoint='gst-eway-print',
            ewbNumber='123456789012',
            nicUsername='api_nic_user',
            nicPassword='api_nic_pass',
            gstin='27AAAAA0000A1Z5',
        )
        self.assertEqual(response.status_code, 403)
        mock_print.assert_not_called()

    @patch('gst.lookup_handlers.MyGSTCafePrintClient.get_eway_detailed_print')
    def test_portal_try_uses_profile_gstin_for_print(self, mock_print):
        _complete_profile(self.tenant)
        mock_print.return_value = b'%PDF-1.4 eway'
        response = _portal_post(
            self.client,
            endpoint='gst-eway-print',
            ewbNumber='123456789012',
            gstin='27AAAAA0000A1Z5',
        )
        self.assertEqual(response.status_code, 200)
        mock_print.assert_called_once_with(
            '123456789012',
            get_company_profile(self.tenant).gstin,
            nic_username='nic_user',
            nic_password='nic_secret',
        )


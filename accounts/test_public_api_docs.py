from django.test import TestCase


class PublicApiDocsTests(TestCase):
    def test_public_api_docs_page_loads(self):
        response = self.client.get('/api-docs/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'API Documentation')
        self.assertContains(response, 'IG E-Sign')
        self.assertContains(response, 'api-docs-catalog')
        self.assertContains(response, 'Sign a PDF')
        self.assertContains(response, 'Get GSTIN details')
        self.assertContains(response, 'Print E-WAY bill')
        self.assertContains(response, 'Print e-invoice (IRN)')
        self.assertContains(response, 'api-docs-snippets.js')
        self.assertContains(response, 'api-docs-highlight.js')
        self.assertContains(response, 'api-docs-lang-icons.js')
        self.assertContains(response, 'api-docs-lang-tabs')
        self.assertContains(response, 'api-docs-menu-btn')
        self.assertContains(response, 'id="api-docs-export-postman"')

    def test_public_api_docs_no_login_required(self):
        response = self.client.get('/api-docs/')
        self.assertNotContains(response, 'Sign in to continue')

    def test_dashboard_docs_redirects_to_public(self):
        from django.contrib.auth.models import User

        from accounts.models import Tenant, TenantMembership, TenantStatus

        tenant = Tenant.objects.create(
            name='Docs Co',
            slug='docs-co',
            status=TenantStatus.ACTIVE,
            quota_reset_at='2099-01-01T00:00:00Z',
        )
        user = User.objects.create_user(username='u@test.com', email='u@test.com', password='pass')
        TenantMembership.objects.create(tenant=tenant, user=user, role='owner', is_primary=True)
        self.client.login(username='u@test.com', password='pass')
        response = self.client.get('/dashboard/docs/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/api-docs/')

    def test_usb_catalog_documents_server_side_poll_and_agent_origin(self):
        from accounts.api_docs_catalog import build_api_docs_catalog, get_catalog_item

        catalog = build_api_docs_catalog('https://sign.example.com')
        overview = get_catalog_item(catalog, 'usb-overview')
        local_agent = get_catalog_item(catalog, 'usb-local-agent')
        health = get_catalog_item(catalog, 'usb-local-agent-health')
        download = get_catalog_item(catalog, 'usb-download')

        self.assertIn('server vs browser', overview['sections'][1]['title'].lower())
        self.assertNotIn('api_base', local_agent['request_json'])
        self.assertIn('Origin:', local_agent['curl'])
        self.assertIn('hash_after', local_agent['response_success_json'])
        self.assertNotIn('Signing started', local_agent['response_success_json'])
        self.assertTrue(any(p['name'] == 'Origin' for p in local_agent['parameters']))
        self.assertIn('Origin header is required', local_agent['response_error_json'])
        self.assertIn('synchronous', local_agent['description'].lower())
        self.assertEqual(health['method'], 'GET')
        self.assertIn('portal_paired', health['response_success_json'])
        self.assertIn('job_id', download['response_success_json'])
        self.assertIn('hash_after_prefix', download['response_success_json'])

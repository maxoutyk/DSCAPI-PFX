from django.test import TestCase


class PublicApiDocsTests(TestCase):
    def test_public_api_docs_page_loads(self):
        response = self.client.get('/api-docs/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'IG E-Sign API')
        self.assertContains(response, 'api-docs-catalog')
        self.assertContains(response, 'Sign a PDF')
        self.assertContains(response, 'Get GSTIN details')
        self.assertContains(response, 'api-docs-snippets.js')
        self.assertContains(response, 'api-docs-highlight.js')
        self.assertContains(response, 'api-docs-lang-icons.js')
        self.assertContains(response, 'api-docs-lang-tabs')
        self.assertContains(response, 'api-docs-menu-btn')
        self.assertContains(response, 'Export Postman')
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

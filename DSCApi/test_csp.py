from django.test import Client, RequestFactory, SimpleTestCase, TestCase

from DSCApi.csp import csp_header_value, generate_csp_nonce, should_apply_csp
from DSCApi.middleware import ContentSecurityPolicyMiddleware


class CspHelperTests(SimpleTestCase):
    def test_generate_nonce_is_unique_and_nonempty(self):
        a = generate_csp_nonce()
        b = generate_csp_nonce()
        self.assertTrue(a)
        self.assertTrue(b)
        self.assertNotEqual(a, b)

    def test_csp_header_uses_nonce_and_blocks_inline_scripts(self):
        nonce = 'test-nonce-value'
        header = csp_header_value(nonce)
        self.assertIn(f"'nonce-{nonce}'", header)
        self.assertIn("script-src 'self'", header)
        self.assertNotIn("'unsafe-inline'", header.split('script-src')[1].split(';')[0])
        self.assertIn("style-src 'self' 'unsafe-inline'", header)
        self.assertIn("object-src 'none'", header)

    def test_should_apply_csp_skips_admin_and_static(self):
        self.assertFalse(should_apply_csp('/admin/'))
        self.assertFalse(should_apply_csp('/admin/login/'))
        self.assertFalse(should_apply_csp('/static/accounts/js/shell.js'))
        self.assertTrue(should_apply_csp('/login/'))
        self.assertTrue(should_apply_csp('/sign/'))


class ContentSecurityPolicyMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = ContentSecurityPolicyMiddleware(lambda request: self._ok_response())

    def _ok_response(self):
        from django.http import HttpResponse

        return HttpResponse('ok')

    def test_middleware_sets_request_nonce(self):
        request = self.factory.get('/login/')
        self.middleware(request)
        self.assertTrue(getattr(request, 'csp_nonce', ''))

    def test_middleware_adds_header_for_portal_pages(self):
        client = Client()
        response = client.get('/login/')
        self.assertEqual(response.status_code, 200)
        csp = response.headers.get('Content-Security-Policy', '')
        self.assertTrue(csp)
        self.assertIn("'nonce-", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)

    def test_middleware_skips_admin(self):
        client = Client()
        response = client.get('/admin/login/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Content-Security-Policy', response.headers)

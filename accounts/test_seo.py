from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.seo import build_canonical_url, page_meta_for_request, robots_txt_lines, should_noindex


class SeoHelperTests(TestCase):
    @override_settings(SITE_URL='https://sign.example.com')
    def test_robots_txt_includes_sitemap_and_disallows_private_routes(self):
        lines = '\n'.join(robots_txt_lines())
        self.assertIn('Sitemap: https://sign.example.com/sitemap.xml', lines)
        self.assertIn('Disallow: /dashboard/', lines)
        self.assertIn('Disallow: /api/', lines)
        self.assertIn('Disallow: /admin/', lines)

    @override_settings(SITE_URL='https://sign.example.com')
    def test_build_canonical_url_normalizes_trailing_slash(self):
        request = self.client.get('/api-docs').wsgi_request
        self.assertEqual(build_canonical_url(request), 'https://sign.example.com/api-docs/')

    @override_settings(SITE_URL='https://sign.example.com')
    def test_home_page_meta(self):
        response = self.client.get('/')
        request = response.wsgi_request
        meta = page_meta_for_request(request)
        self.assertIn('Digital PDF Signing', meta['title'])
        self.assertIn('Class 3 DSC', meta['description'])

    def test_should_noindex_dashboard(self):
        request = self.client.get('/dashboard/').wsgi_request
        self.assertTrue(should_noindex(request))

    def test_public_sign_free_is_indexable(self):
        request = self.client.get('/sign/free/').wsgi_request
        self.assertFalse(should_noindex(request))


class SeoEndpointTests(TestCase):
    @override_settings(SITE_URL='https://sign.example.com')
    def test_robots_txt_endpoint(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn('User-agent: *', response.content.decode())

    @override_settings(SITE_URL='https://sign.example.com')
    def test_sitemap_xml_lists_public_pages(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('<loc>https://sign.example.com/</loc>', body)
        self.assertIn('<loc>https://sign.example.com/features/</loc>', body)
        self.assertIn('<loc>https://sign.example.com/pricing/</loc>', body)
        self.assertIn('<loc>https://sign.example.com/blog/</loc>', body)
        self.assertIn(
            '<loc>https://sign.example.com/blog/class-3-dsc-usb-token-signing/</loc>',
            body,
        )
        self.assertIn(
            '<loc>https://sign.example.com/blog/eway-bill-and-einvoice-pdf-print/</loc>',
            body,
        )
        self.assertNotIn('/compare/docusign-alternative/', body)
        self.assertIn('<loc>https://sign.example.com/legal/privacy/</loc>', body)
        self.assertNotIn('/dashboard/', body)

    @override_settings(SITE_URL='https://sign.example.com')
    def test_marketing_features_page(self):
        response = self.client.get('/features/')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('application/ld+json', body)
        self.assertIn('Class 3 USB DSC', body)
        self.assertIn('rel="canonical" href="https://sign.example.com/features/"', body)

    @override_settings(SITE_URL='https://sign.example.com')
    def test_marketing_features_visible_when_logged_in(self):
        from django.contrib.auth.models import User

        user = User.objects.create_user(username='seo@example.com', email='seo@example.com', password='pass')
        self.client.login(username='seo@example.com', password='pass')
        response = self.client.get('/features/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Class 3 USB DSC', response.content.decode())
        self.assertIn('marketing-page', response.content.decode())

    @override_settings(SITE_URL='https://sign.example.com')
    def test_marketing_pricing_page_has_faq_schema(self):
        response = self.client.get('/pricing/')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('FAQPage', body)
        self.assertIn('100 signatures', body)

    @override_settings(SITE_URL='https://sign.example.com')
    def test_homepage_has_json_ld(self):
        response = self.client.get('/')
        body = response.content.decode()
        self.assertIn('SoftwareApplication', body)
        self.assertIn('Organization', body)

    @override_settings(SITE_URL='https://sign.example.com')
    def test_homepage_has_canonical_and_meta_description(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('rel="canonical" href="https://sign.example.com/"', body)
        self.assertIn('<meta name="description"', body)
        self.assertIn('E-way bill', body)
        self.assertIn('e-invoice', body)
        self.assertIn('index, follow', body)

    @override_settings(SITE_URL='https://sign.example.com')
    def test_homepage_shows_microsoft_store_agent_link(self):
        from usb_agent.distribution import microsoft_store_agent_url

        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, microsoft_store_agent_url())
        self.assertContains(response, 'Get from Microsoft Store')

    @override_settings(SITE_URL='https://sign.example.com')
    def test_api_docs_has_canonical(self):
        response = self.client.get(reverse('public_api_docs'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('rel="canonical" href="https://sign.example.com/api-docs/"', body)

    @override_settings(SITE_URL='https://sign.example.com')
    def test_password_reset_is_noindex(self):
        response = self.client.get('/password-reset/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('noindex', response.content.decode())

    @override_settings(SITE_URL='https://sign.example.com')
    def test_og_image_is_social_card(self):
        response = self.client.get('/')
        body = response.content.decode()
        self.assertIn('og-default.png', body)
        self.assertIn('og:image:width" content="1200"', body)
        self.assertIn('og:image:height" content="630"', body)

    @override_settings(SITE_URL='https://sign.example.com', GOOGLE_SITE_VERIFICATION='gsc-token-123')
    def test_google_site_verification_meta(self):
        response = self.client.get('/')
        self.assertIn(
            'name="google-site-verification" content="gsc-token-123"',
            response.content.decode(),
        )

    @override_settings(SITE_URL='https://sign.example.com')
    def test_blog_index_and_post(self):
        index = self.client.get('/blog/')
        self.assertEqual(index.status_code, 200)
        self.assertIn('Class 3 DSC USB token signing', index.content.decode())

        post = self.client.get('/blog/class-3-dsc-usb-token-signing/')
        self.assertEqual(post.status_code, 200)
        body = post.content.decode()
        self.assertIn('Article', body)
        self.assertIn('og:type" content="article"', body)
        self.assertIn('PKCS#11', body)
        self.assertIn(
            'rel="canonical" href="https://sign.example.com/blog/class-3-dsc-usb-token-signing/"',
            body,
        )

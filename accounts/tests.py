from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .emailing import resend_verification_email, send_password_reset_email, send_verification_email
from .models import EmailVerificationToken, PasswordResetToken, Tenant, TenantMembership, TenantStatus
from .services import (
    PasswordResetTokenExpiredError,
    VerificationTokenExpiredError,
    authenticate_api_key,
    create_api_key,
    encrypt_pfx,
    decrypt_pfx,
    get_stored_certificate_bytes,
    register_tenant,
    request_password_reset,
    reset_password_with_token,
    store_certificate,
    verify_email,
)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RegistrationFlowTests(TestCase):
    def test_register_and_verify_email(self):
        tenant = register_tenant(
            email='owner@example.com',
            password='secure-pass-123',
            organization_name='Acme Corp',
        )
        self.assertEqual(tenant.status, TenantStatus.PENDING_EMAIL)
        user = User.objects.get(email='owner@example.com')
        self.assertFalse(user.is_active)

        token = user.email_tokens.first()
        verified = verify_email(token.token)
        self.assertEqual(verified.status, TenantStatus.PENDING_APPROVAL)
        user.refresh_from_db()
        self.assertTrue(user.is_active)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    SITE_URL='https://app.example.com',
    DEFAULT_FROM_EMAIL='noreply@example.com',
)
class VerificationEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='verify@example.com',
            email='verify@example.com',
            password='secure-pass-123',
            is_active=False,
        )
        self.tenant = Tenant.objects.create(
            name='Verify Org',
            slug='verify-org',
            status=TenantStatus.PENDING_EMAIL,
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role='owner',
            is_primary=True,
        )

    def test_send_verification_email_html_and_text(self):
        send_verification_email(self.user)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, 'Verify your IG E-Sign account')
        self.assertIn('https://app.example.com/verify-email/', message.body)
        self.assertEqual(len(message.alternatives), 1)
        html, content_type = message.alternatives[0]
        self.assertEqual(content_type, 'text/html')
        self.assertIn('Verify your IG E-Sign account', html)

    def test_resend_verification_email_replaces_old_token(self):
        send_verification_email(self.user)
        first_token = self.user.email_tokens.first().token
        self.assertTrue(resend_verification_email(self.user.email))
        self.assertEqual(len(mail.outbox), 2)
        active_tokens = EmailVerificationToken.objects.filter(user=self.user, used_at__isnull=True)
        self.assertEqual(active_tokens.count(), 1)
        self.assertNotEqual(active_tokens.first().token, first_token)

    def test_resend_verification_unknown_email_returns_false(self):
        self.assertFalse(resend_verification_email('nobody@example.com'))
        self.assertEqual(len(mail.outbox), 0)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    SITE_URL='https://app.example.com',
)
class ResendVerificationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='pending@example.com',
            email='pending@example.com',
            password='secure-pass-123',
            is_active=False,
        )
        self.tenant = Tenant.objects.create(
            name='Pending Org',
            slug='pending-org',
            status=TenantStatus.PENDING_EMAIL,
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role='owner',
            is_primary=True,
        )
        self.client = Client()

    def test_resend_verification_view_sends_email(self):
        response = self.client.post(
            '/resend-verification/',
            {'email': 'pending@example.com'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Check your email')
        self.assertEqual(len(mail.outbox), 1)

    def test_login_shows_helpful_message_for_unverified_user(self):
        response = self.client.post(
            '/login/',
            {'username': 'pending@example.com', 'password': 'secure-pass-123'},
        )
        self.assertContains(response, 'Verify your email before signing in')
        self.assertContains(response, 'Resend verification')


class APIKeyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Test Org',
            slug='test-org',
            status=TenantStatus.ACTIVE,
        )

    def test_create_and_authenticate_api_key(self):
        api_key, full_key = create_api_key(self.tenant, 'Test Key')
        result = authenticate_api_key(full_key)
        self.assertIsNotNone(result)
        matched_key, tenant = result
        self.assertEqual(matched_key.pk, api_key.pk)
        self.assertEqual(tenant.pk, self.tenant.pk)


class CertificateEncryptionTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Test Org', slug='test-org-2', status=TenantStatus.ACTIVE)

    def test_store_and_retrieve_certificate(self):
        original = b'fake-pfx-bytes'
        store_certificate(self.tenant, 'company-dsc', original)
        retrieved = get_stored_certificate_bytes(self.tenant, 'company-dsc')
        self.assertEqual(retrieved, original)

    def test_encrypt_decrypt_roundtrip(self):
        data = b'secret-cert-data'
        encrypted = encrypt_pfx(data)
        self.assertNotEqual(encrypted, data)
        self.assertEqual(decrypt_pfx(encrypted), data)

    def test_decrypt_accepts_memoryview(self):
        data = b'secret-cert-data'
        encrypted = encrypt_pfx(data)
        self.assertEqual(decrypt_pfx(memoryview(encrypted)), data)


@override_settings(VERIFY_EMAIL_TOKEN_HOURS=24)
class VerificationTokenSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='expired@example.com',
            email='expired@example.com',
            password='secure-pass-123',
            is_active=False,
        )
        self.tenant = Tenant.objects.create(
            name='Expired Org',
            slug='expired-org',
            status=TenantStatus.PENDING_EMAIL,
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role='owner',
            is_primary=True,
        )
        self.token = EmailVerificationToken.objects.create(user=self.user)

    def test_expired_verification_token_rejected(self):
        EmailVerificationToken.objects.filter(pk=self.token.pk).update(
            created_at=timezone.now() - timedelta(hours=25),
        )
        self.token.refresh_from_db()
        with self.assertRaises(VerificationTokenExpiredError):
            verify_email(self.token.token)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    SITE_URL='https://app.example.com',
    DEFAULT_FROM_EMAIL='noreply@example.com',
)
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='reset@example.com',
            email='reset@example.com',
            password='old-password-123',
            is_active=True,
        )
        self.tenant = Tenant.objects.create(
            name='Reset Org',
            slug='reset-org',
            status=TenantStatus.ACTIVE,
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role='owner',
            is_primary=True,
        )

    def test_request_password_reset_sends_email(self):
        request_password_reset(self.user.email)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Reset your IG E-Sign password', mail.outbox[0].subject)
        self.assertIn('/reset-password/', mail.outbox[0].body)

    def test_request_password_reset_unknown_email_silent(self):
        request_password_reset('nobody@example.com')
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_password_with_token(self):
        send_password_reset_email(self.user)
        token = self.user.password_reset_tokens.first().token
        reset_password_with_token(token, 'new-secure-pass-99')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('new-secure-pass-99'))
        self.assertIsNotNone(self.user.password_reset_tokens.first().used_at)

    def test_expired_reset_token_rejected(self):
        send_password_reset_email(self.user)
        token = self.user.password_reset_tokens.first()
        PasswordResetToken.objects.filter(pk=token.pk).update(
            created_at=timezone.now() - timedelta(hours=3),
        )
        token.refresh_from_db()
        with self.assertRaises(PasswordResetTokenExpiredError):
            reset_password_with_token(token.token, 'new-secure-pass-99')

    def test_password_reset_confirm_page(self):
        send_password_reset_email(self.user)
        token = self.user.password_reset_tokens.first().token
        client = Client()
        response = client.post(
            f'/reset-password/{token}/',
            {'password': 'brand-new-pass', 'password_confirm': 'brand-new-pass'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/login/')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('brand-new-pass'))


class DisplayTimezoneFilterTests(TestCase):
    def test_ist_filter_converts_utc_to_india_time(self):
        from accounts.templatetags.display_tz import ist

        utc = datetime(2026, 6, 9, 12, 30, tzinfo=ZoneInfo('UTC'))
        self.assertEqual(ist(utc, 'M j, H:i'), 'Jun 9, 18:00')

    def test_ist_filter_returns_empty_for_none(self):
        from accounts.templatetags.display_tz import ist

        self.assertEqual(ist(None), '')


@override_settings(RATELIMIT_DEFAULT_LIMIT=2, RATELIMIT_DEFAULT_PERIOD=900)
class PortalRateLimitTests(TestCase):
    def test_login_rate_limit_blocks_after_failures(self):
        client = Client()
        for _ in range(2):
            client.post('/login/', {'username': 'nobody@example.com', 'password': 'wrong'})
        response = client.post('/login/', {'username': 'nobody@example.com', 'password': 'wrong'})
        self.assertContains(response, 'Too many attempts')

    def test_login_survives_cache_backend_failure(self):
        from unittest.mock import patch

        client = Client()
        with patch('django.core.cache.cache.get', side_effect=Exception('cache down')):
            response = client.post('/login/', {'username': 'nobody@example.com', 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)


class ApiDocsDownloadTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Docs Org',
            slug='docs-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=250,
        )
        self.user = User.objects.create_user(
            username='docs@example.com',
            email='docs@example.com',
            password='docs-pass',
            is_active=True,
        )
        TenantMembership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role='owner',
            is_primary=True,
        )
        self.client = Client()

    def test_download_requires_login(self):
        response = self.client.get('/dashboard/docs/download/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_download_returns_pdf_attachment(self):
        import fitz

        self.client.login(username='docs@example.com', password='docs-pass')
        response = self.client.get('/dashboard/docs/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('ig-esign-api-docs.pdf', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))
        doc = fitz.open(stream=response.content, filetype='pdf')
        try:
            text = ''.join(page.get_text() for page in doc)
        finally:
            doc.close()
        self.assertIn('POST /api/sign/usb/', text)
        self.assertIn('sign_token', text)
        self.assertIn('250', text)
        self.assertIn('Download API docs (PDF)', self.client.get('/dashboard/docs/').content.decode())

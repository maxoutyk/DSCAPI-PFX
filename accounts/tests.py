from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .emailing import resend_verification_email, send_password_reset_email, send_verification_email
from .models import EmailVerificationToken, MembershipRole, PasswordResetToken, Tenant, TenantMembership, TenantStatus, UsageLog
from .services import (
    PasswordResetTokenExpiredError,
    VerificationTokenExpiredError,
    authenticate_api_key,
    build_monthly_usage_report,
    create_api_key,
    encrypt_pfx,
    decrypt_pfx,
    get_stored_certificate_bytes,
    register_tenant,
    request_password_reset,
    reset_password_with_token,
    store_certificate,
    update_api_key_customer_label,
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
        api_key, full_key = create_api_key(self.tenant, 'Test Key', customer_label='Acme Corp')
        self.assertEqual(api_key.customer_label, 'Acme Corp')
        result = authenticate_api_key(full_key)
        self.assertIsNotNone(result)
        matched_key, tenant = result
        self.assertEqual(matched_key.pk, api_key.pk)
        self.assertEqual(tenant.pk, self.tenant.pk)

    def test_update_api_key_customer_label(self):
        api_key, _full_key = create_api_key(self.tenant, 'Test Key')
        update_api_key_customer_label(api_key, '  Widget Inc  ')
        api_key.refresh_from_db()
        self.assertEqual(api_key.customer_label, 'Widget Inc')


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

    def test_dashboard_docs_redirects_to_public_catalog(self):
        self.client.login(username='docs@example.com', password='docs-pass')
        response = self.client.get('/dashboard/docs/', follow=True)
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        self.assertIn('Sign a PDF', text)
        self.assertIn('Get GSTIN details', text)


class PortalSecurityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner@example.com',
            email='owner@example.com',
            password='owner-pass',
            is_active=True,
        )
        self.member = User.objects.create_user(
            username='member@example.com',
            email='member@example.com',
            password='member-pass',
            is_active=True,
        )
        self.tenant = Tenant.objects.create(
            name='Sec Org',
            slug='sec-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )
        TenantMembership.objects.create(
            user=self.owner,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
            is_primary=True,
        )
        TenantMembership.objects.create(
            user=self.member,
            tenant=self.tenant,
            role=MembershipRole.MEMBER,
            is_primary=True,
        )
        self.client = Client()

    def test_dashboard_redirects_without_tenant_membership(self):
        orphan = User.objects.create_user(
            username='orphan@example.com',
            email='orphan@example.com',
            password='orphan-pass',
            is_active=True,
        )
        self.client.login(username='orphan@example.com', password='orphan-pass')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

    def test_member_cannot_create_api_key(self):
        self.client.login(username='member@example.com', password='member-pass')
        response = self.client.post('/dashboard/keys/', {'name': 'blocked'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/')
        self.assertEqual(self.tenant.api_keys.count(), 0)

    def test_member_cannot_view_certificates_page(self):
        self.client.login(username='member@example.com', password='member-pass')
        response = self.client.get('/dashboard/certs/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/')

    def test_owner_can_create_api_key(self):
        self.client.login(username='owner@example.com', password='owner-pass')
        response = self.client.post(
            '/dashboard/keys/',
            {'name': 'allowed', 'customer_label': 'Acme Ltd'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.tenant.api_keys.count(), 1)
        self.assertEqual(self.tenant.api_keys.get().customer_label, 'Acme Ltd')

    def test_owner_can_update_customer_label(self):
        self.client.login(username='owner@example.com', password='owner-pass')
        api_key, _ = create_api_key(self.tenant, 'Prod')
        response = self.client.post(
            '/dashboard/keys/',
            {'update_customer_label': api_key.pk, 'customer_label': 'Beta Customer'},
        )
        self.assertEqual(response.status_code, 302)
        api_key.refresh_from_db()
        self.assertEqual(api_key.customer_label, 'Beta Customer')


class UsageReportTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Usage Org',
            slug='usage-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )
        self.key_a, _ = create_api_key(self.tenant, 'Key A', customer_label='Customer A')
        self.key_b, _ = create_api_key(self.tenant, 'Key B', customer_label='Customer B')

    def test_build_monthly_usage_report_groups_by_key_and_portal(self):
        from gst.models import GstApiLog

        UsageLog.objects.create(tenant=self.tenant, api_key=self.key_a, success=True)
        UsageLog.objects.create(tenant=self.tenant, api_key=self.key_a, success=True)
        UsageLog.objects.create(tenant=self.tenant, api_key=None, success=True)
        UsageLog.objects.create(tenant=self.tenant, api_key=self.key_b, success=False)
        GstApiLog.objects.create(
            tenant=self.tenant,
            endpoint='gstin',
            api_key=self.key_b,
            success=True,
        )

        report = build_monthly_usage_report(self.tenant)
        by_customer = {row['customer_label']: row for row in report['rows']}

        self.assertEqual(by_customer['Customer A']['signing_count'], 2)
        self.assertEqual(by_customer['Customer A']['gst_count'], 0)
        self.assertEqual(by_customer['Customer A']['total'], 2)
        self.assertEqual(by_customer['Customer B']['signing_count'], 0)
        self.assertEqual(by_customer['Customer B']['gst_count'], 1)
        self.assertEqual(by_customer['Portal']['signing_count'], 1)
        self.assertEqual(report['total_usage'], 4)
        self.assertEqual(len(report['daily_overall']), len([d for d in report['daily_overall']]))
        self.assertTrue(any(point['total'] > 0 for point in report['daily_overall']))
        self.assertEqual(len(report['customer_groups']), 3)
        from calendar import monthrange

        from django.utils import timezone

        from accounts.templatetags.display_tz import DISPLAY_TZ

        now = timezone.localtime(timezone.now(), DISPLAY_TZ)
        self.assertEqual(report['period_start_display'].day, 1)
        self.assertEqual(
            report['period_end_display'].day,
            monthrange(now.year, now.month)[1],
        )
        self.assertEqual(len(report['daily_overall']), monthrange(now.year, now.month)[1])

    def test_historical_period_excludes_other_months(self):
        from datetime import datetime

        from django.utils import timezone

        from accounts.templatetags.display_tz import DISPLAY_TZ

        may_time = timezone.make_aware(datetime(2026, 5, 15, 12, 0, 0), DISPLAY_TZ)
        june_time = timezone.make_aware(datetime(2026, 6, 15, 12, 0, 0), DISPLAY_TZ)
        log_may = UsageLog.objects.create(tenant=self.tenant, api_key=self.key_a, success=True)
        UsageLog.objects.filter(pk=log_may.pk).update(created_at=may_time)
        log_june = UsageLog.objects.create(tenant=self.tenant, api_key=self.key_a, success=True)
        UsageLog.objects.filter(pk=log_june.pk).update(created_at=june_time)

        may_report = build_monthly_usage_report(self.tenant, year=2026, month=5)
        june_report = build_monthly_usage_report(self.tenant, year=2026, month=6)

        self.assertEqual(may_report['total_usage'], 1)
        self.assertEqual(june_report['total_usage'], 1)
        self.assertEqual(may_report['period_end_display'].day, 31)
        self.assertFalse(may_report['show_quota'])

    def test_overall_csv_download(self):
        from gst.models import GstApiLog

        owner = User.objects.create_user(
            username='usage-owner@example.com',
            email='usage-owner@example.com',
            password='owner-pass',
            is_active=True,
        )
        TenantMembership.objects.create(
            user=owner,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
            is_primary=True,
        )
        UsageLog.objects.create(tenant=self.tenant, api_key=self.key_a, success=True)
        GstApiLog.objects.create(
            tenant=self.tenant,
            endpoint='gstin',
            api_key=self.key_b,
            success=True,
        )

        client = Client()
        client.login(username='usage-owner@example.com', password='owner-pass')
        response = client.get('/dashboard/usage/download/?scope=overall&format=csv&period=2026-06')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        body = response.content.decode('utf-8-sig')
        self.assertIn('Daily usage', body)
        self.assertIn('Customer A', body)

    def test_customer_pdf_download(self):
        owner = User.objects.create_user(
            username='usage-owner@example.com',
            email='usage-owner@example.com',
            password='owner-pass',
            is_active=True,
        )
        TenantMembership.objects.create(
            user=owner,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
            is_primary=True,
        )
        UsageLog.objects.create(tenant=self.tenant, api_key=self.key_a, success=True)

        client = Client()
        client.login(username='usage-owner@example.com', password='owner-pass')
        response = client.get('/dashboard/usage/download/?scope=customer&bucket=customer-a&format=pdf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        import fitz

        doc = fitz.open(stream=response.content, filetype='pdf')
        try:
            self.assertGreaterEqual(doc.page_count, 1)
            image_count = sum(len(page.get_images()) for page in doc)
            self.assertGreater(image_count, 0)
            text = ''.join(page.get_text() for page in doc)
        finally:
            doc.close()
        self.assertIn('Customer Usage Report', text)
        self.assertIn('Daily usage trend', text)
        self.assertLess(len(response.content), 500 * 1024, 'PDF should stay under 500 KB')

    def test_usage_report_page_renders_for_owner(self):
        owner = User.objects.create_user(
            username='usage-owner@example.com',
            email='usage-owner@example.com',
            password='owner-pass',
            is_active=True,
        )
        TenantMembership.objects.create(
            user=owner,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
            is_primary=True,
        )
        UsageLog.objects.create(tenant=self.tenant, api_key=self.key_a, success=True)

        client = Client()
        client.login(username='usage-owner@example.com', password='owner-pass')
        response = client.get('/dashboard/usage/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Customer A')
        self.assertContains(response, 'usage-period-select')
        self.assertContains(response, 'Period')

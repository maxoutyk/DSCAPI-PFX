from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .models import Tenant, TenantMembership, TenantStatus
from .services import (
    authenticate_api_key,
    create_api_key,
    encrypt_pfx,
    decrypt_pfx,
    get_stored_certificate_bytes,
    register_tenant,
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

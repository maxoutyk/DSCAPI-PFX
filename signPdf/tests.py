import base64

import fitz
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Tenant, TenantStatus
from accounts.services import create_api_key


def _minimal_pdf_base64():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), 'Authorised Signatory')
    data = doc.tobytes()
    doc.close()
    return base64.b64encode(data).decode()


class SignPdfAPIAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name='Test Org',
            slug='test-org-api',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )
        _, self.api_key = create_api_key(self.tenant, 'Integration Test')
        self.pdf_b64 = _minimal_pdf_base64()

    def test_missing_api_key_returns_unauthorized(self):
        response = self.client.post(
            '/api/signpdf-pfx',
            {'pdf_base64': self.pdf_b64, 'pfx_base64': 'abc', 'password': 'x'},
            format='json',
        )
        self.assertIn(response.status_code, [401, 403])

    def test_invalid_api_key_returns_unauthorized(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer dsc_live_invalid-key')
        response = self.client.post(
            '/api/signpdf-pfx',
            {'pdf_base64': self.pdf_b64, 'pfx_base64': 'abc', 'password': 'x'},
            format='json',
        )
        self.assertIn(response.status_code, [401, 403])

    def test_pending_approval_tenant_returns_403(self):
        self.tenant.status = TenantStatus.PENDING_APPROVAL
        self.tenant.save(update_fields=['status'])
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.api_key}')
        response = self.client.post(
            '/api/signpdf-pfx',
            {'pdf_base64': self.pdf_b64, 'pfx_base64': 'YWJj', 'password': 'x'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn('approval', response.json()['error'].lower())

    def test_requires_exactly_one_cert_source(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.api_key}')
        response = self.client.post(
            '/api/signpdf-pfx',
            {'pdf_base64': self.pdf_b64, 'password': 'x'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_pfx_path_rejected_for_api_key_auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.api_key}')
        response = self.client.post(
            '/api/signpdf-pfx',
            {
                'pdf_base64': self.pdf_b64,
                'pfx_path': 'test.pfx',
                'password': 'x',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('pfx_path', response.json())

    @override_settings(ALLOW_BASIC_AUTH=False)
    def test_basic_auth_rejected_when_disabled(self):
        User.objects.create_user(
            username='portal@example.com',
            email='portal@example.com',
            password='secure-pass-123',
            is_active=True,
        )
        self.client.credentials(
            HTTP_AUTHORIZATION='Basic ' + base64.b64encode(b'portal@example.com:secure-pass-123').decode(),
        )
        response = self.client.post(
            '/api/signpdf-pfx',
            {'pdf_base64': self.pdf_b64, 'pfx_base64': 'YWJj', 'password': 'x'},
            format='json',
        )
        self.assertIn(response.status_code, [401, 403])

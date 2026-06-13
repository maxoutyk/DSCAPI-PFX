import base64

import fitz
from django.test import RequestFactory, TestCase, override_settings

from accounts.models import DocumentType, Tenant, TenantStatus, UsageLog
from accounts.services import create_api_key
from signPdf.audit import get_client_ip, sha256_hex
from signPdf.document_detection import detect_document_type, normalize_pdf_text


def _pdf_with_text(*lines: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 24
    data = doc.tobytes()
    doc.close()
    return data


class Sha256Tests(TestCase):
    def test_sha256_hex_is_lowercase_64_chars(self):
        digest = sha256_hex(b'hello')
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, digest.lower())


class ClientIpTests(TestCase):
    def test_ignores_forwarded_ip_without_trusted_proxy(self):
        request = RequestFactory().post(
            '/api/signpdf-pfx',
            HTTP_X_FORWARDED_FOR='203.0.113.1, 10.0.0.1',
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(get_client_ip(request), '127.0.0.1')

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_uses_forwarded_ip_behind_one_proxy(self):
        request = RequestFactory().post('/api/signpdf-pfx', HTTP_X_FORWARDED_FOR='203.0.113.1')
        self.assertEqual(get_client_ip(request), '203.0.113.1')

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_skips_loopback_forwarded_ip(self):
        request = RequestFactory().post(
            '/api/signpdf-pfx',
            HTTP_X_FORWARDED_FOR='127.0.0.1, 203.0.113.1',
            HTTP_X_REAL_IP='203.0.113.1',
        )
        self.assertEqual(get_client_ip(request), '203.0.113.1')

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_uses_x_real_ip_when_forwarded_is_loopback_only(self):
        request = RequestFactory().post(
            '/api/signpdf-pfx',
            HTTP_X_FORWARDED_FOR='127.0.0.1',
            HTTP_X_REAL_IP='203.0.113.44',
        )
        self.assertEqual(get_client_ip(request), '203.0.113.44')

    def test_falls_back_to_remote_addr(self):
        request = RequestFactory().post('/api/signpdf-pfx', REMOTE_ADDR='198.51.100.9')
        self.assertEqual(get_client_ip(request), '198.51.100.9')

    def test_keeps_loopback_when_no_external_ip_available(self):
        request = RequestFactory().post(
            '/dashboard/sign/',
            HTTP_X_FORWARDED_FOR='127.0.0.1',
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(get_client_ip(request), '127.0.0.1')


class DocumentDetectionTests(TestCase):
    def test_detects_tax_invoice(self):
        pdf_data = _pdf_with_text('TAX INVOICE', 'Authorised Signatory')
        result = detect_document_type(pdf_data)
        self.assertEqual(result.document_type, DocumentType.TAX_INVOICE)
        self.assertEqual(result.detected_keyword, 'TAX INVOICE')
        self.assertEqual(result.detection_confidence, 'high')

    def test_detects_purchase_order(self):
        pdf_data = _pdf_with_text('PURCHASE ORDER NO 123', 'Authorised Signatory')
        result = detect_document_type(pdf_data)
        self.assertEqual(result.document_type, DocumentType.PURCHASE_ORDER)

    def test_unknown_when_no_keywords(self):
        pdf_data = _pdf_with_text('Random document', 'Authorised Signatory')
        result = detect_document_type(pdf_data)
        self.assertEqual(result.document_type, DocumentType.UNKNOWN)
        self.assertEqual(result.detection_confidence, 'none')

    def test_low_confidence_when_multiple_types_present(self):
        pdf_data = _pdf_with_text('TAX INVOICE', 'QUOTATION NO 55', 'Authorised Signatory')
        result = detect_document_type(pdf_data)
        self.assertEqual(result.document_type, DocumentType.TAX_INVOICE)
        self.assertEqual(result.detection_confidence, 'low')

    def test_normalize_collapses_whitespace(self):
        self.assertEqual(normalize_pdf_text('tax   invoice'), 'TAX INVOICE')


class SigningAuditIntegrationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Audit Org',
            slug='audit-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )
        _, self.api_key = create_api_key(self.tenant, 'Audit Test')

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_failed_sign_records_hash_and_document_type(self):
        from rest_framework.test import APIClient

        pdf_b64 = base64.b64encode(
            _pdf_with_text('DELIVERY CHALLAN', 'Authorised Signatory'),
        ).decode()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.api_key}')
        response = client.post(
            '/api/signpdf-pfx',
            {'pdf_base64': pdf_b64, 'pfx_base64': 'not-valid-pfx', 'password': 'x'},
            format='json',
            HTTP_X_FORWARDED_FOR='203.0.113.50',
        )
        self.assertEqual(response.status_code, 400)

        log = UsageLog.objects.get(tenant=self.tenant)
        self.assertFalse(log.success)
        self.assertEqual(log.endpoint, 'signpdf-pfx')
        self.assertEqual(log.signing_source, 'api')
        self.assertEqual(log.document_type, DocumentType.DELIVERY_CHALLAN)
        self.assertEqual(log.client_ip, '203.0.113.50')
        self.assertIsNotNone(log.hash_before)
        self.assertEqual(len(log.hash_before), 64)
        self.assertIsNone(log.hash_after)
        self.assertIsNotNone(log.api_key)
        self.assertIsNone(log.user)

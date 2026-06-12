import base64
import fitz
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from accounts.models import DocumentType, MembershipRole, Tenant, TenantMembership, TenantStatus, UsageLog
from accounts.services import store_certificate
from signPdf.pdf_signing import load_pfx_credentials


def _pdf_with_anchor(text='Authorised Signatory') -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 500), 'TAX INVOICE')
    page.insert_text((72, 550), text)
    data = doc.tobytes()
    doc.close()
    return data


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    PORTAL_SIGN_MAX_UPLOAD_BYTES=10 * 1024 * 1024,
)
class PortalSignTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Portal Org',
            slug='portal-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )
        self.user = User.objects.create_user(
            username='portal@example.com',
            email='portal@example.com',
            password='portal-pass',
            is_active=True,
        )
        TenantMembership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
            is_primary=True,
        )
        self.client = Client()
        self.client.login(username='portal@example.com', password='portal-pass')

        pfx_path = __import__('pathlib').Path(__file__).resolve().parents[1] / 'certs' / 'e-Mudhra Sub CA.pfx'
        if pfx_path.is_file():
            pfx_bytes = pfx_path.read_bytes()
            load_pfx_credentials(pfx_bytes, 'emudhra')
            store_certificate(self.tenant, 'emudratest', pfx_bytes)
            self.pfx_password = 'emudhra'
            self.has_pfx = True
        else:
            self.has_pfx = False

    def test_sign_page_requires_login(self):
        anon = Client()
        response = anon.get('/dashboard/sign/')
        self.assertEqual(response.status_code, 302)

    def test_preview_returns_analysis(self):
        if not self.has_pfx:
            self.skipTest('PFX cert not available locally')
        pdf = _pdf_with_anchor()
        response = self.client.post(
            '/dashboard/sign/preview/',
            {'pdf_file': __import__('django.core.files.uploadedfile', fromlist=['SimpleUploadedFile']).SimpleUploadedFile(
                'invoice.pdf', pdf, content_type='application/pdf',
            )},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ready'])
        self.assertGreaterEqual(data['signature_slots'], 1)
        self.assertEqual(data['document_type_label'], 'Tax Invoice')

    def test_portal_sign_creates_audit_log(self):
        if not self.has_pfx:
            self.skipTest('PFX cert not available locally')
        pdf = _pdf_with_anchor()
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = self.client.post(
            '/dashboard/sign/',
            {
                'pdf_file': SimpleUploadedFile('invoice.pdf', pdf, content_type='application/pdf'),
                'cert_alias': 'emudratest',
                'password': self.pfx_password,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/sign/done/')

        log = UsageLog.objects.filter(tenant=self.tenant, endpoint='sign-portal').latest('pk')
        self.assertTrue(log.success)
        self.assertEqual(log.document_type, DocumentType.TAX_INVOICE)
        self.assertEqual(log.user, self.user)
        self.assertIsNotNone(log.hash_after)

        done = self.client.get('/dashboard/sign/done/')
        self.assertEqual(done.status_code, 200)
        self.assertContains(done, 'Download signed PDF')

        download = self.client.get('/dashboard/sign/download/')
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download['Content-Type'], 'application/pdf')
        self.assertGreater(len(download.content), 1000)

import base64

import fitz
from django.contrib.auth.models import User
from django.test import Client, TestCase
from rest_framework.test import APIClient

from accounts.models import DocumentType, MembershipRole, Tenant, TenantMembership, TenantStatus, UsageLog
from accounts.services import store_certificate
from signPdf.pdf_signing import load_pfx_credentials
from signPdf.signing_service import sign_pdf_for_tenant
from signPdf.audit import SigningAuditMeta

from .models import AgentDevice, UsbSignJob, UsbSignJobStatus
from .services import create_pairing_code, pair_device, prepare_usb_sign_job


def _pdf_with_anchor() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), 'TAX INVOICE')
    page.insert_text((72, 120), 'Authorised Signatory')
    data = doc.tobytes()
    doc.close()
    return data


class UsbAgentFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='usb@example.com', email='usb@example.com', password='pass')
        self.tenant = Tenant.objects.create(
            name='USB Org',
            slug='usb-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=MembershipRole.OWNER,
            is_primary=True,
        )
        self.client = Client()
        self.client.login(username='usb@example.com', password='pass')
        self.api = APIClient()

        pfx_path = __import__('pathlib').Path(__file__).resolve().parents[1] / 'certs' / 'e-Mudhra Sub CA.pfx'
        if pfx_path.is_file():
            pfx_bytes = pfx_path.read_bytes()
            load_pfx_credentials(pfx_bytes, 'emudhra')
            store_certificate(self.tenant, 'emudratest', pfx_bytes)
            self.pfx_password = 'emudhra'
            self.has_pfx = True
        else:
            self.has_pfx = False

    def test_pairing_code_creates_device(self):
        pairing = create_pairing_code(tenant=self.tenant, user=self.user)
        device, token = pair_device(code=pairing.code, machine_name='test-pc', agent_version='0.1.0')
        self.assertTrue(token.startswith('dsc_agent_'))
        self.assertEqual(device.tenant, self.tenant)
        self.assertEqual(AgentDevice.objects.filter(tenant=self.tenant).count(), 1)

    def test_agent_heartbeat_and_usb_sign_job(self):
        if not self.has_pfx:
            self.skipTest('PFX cert not available locally')

        pairing = create_pairing_code(tenant=self.tenant, user=self.user)
        device, token = pair_device(code=pairing.code, machine_name='test-pc', agent_version='0.1.0')
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        heartbeat = self.api.post('/api/agent/heartbeat/', {'agent_version': '0.1.0'}, format='json')
        self.assertEqual(heartbeat.status_code, 200)

        pdf = _pdf_with_anchor()
        job = prepare_usb_sign_job(tenant=self.tenant, user=self.user, pdf_data=pdf)
        fetch = self.api.get(f'/api/agent/jobs/{job.id}/')
        self.assertEqual(fetch.status_code, 200)
        self.assertIn('pdf_base64', fetch.json())

        audit = SigningAuditMeta(endpoint='signpdf-pfx', user=self.user)
        signed = sign_pdf_for_tenant(
            tenant=self.tenant,
            pdf_data=pdf,
            password=self.pfx_password,
            cert_alias='emudratest',
            audit=audit,
        )
        complete = self.api.post(
            f'/api/agent/jobs/{job.id}/complete/',
            {'signed_pdf_base64': base64.b64encode(signed.signed_pdf_data).decode('ascii')},
            format='json',
        )
        self.assertEqual(complete.status_code, 200)

        job.refresh_from_db()
        self.assertEqual(job.status, UsbSignJobStatus.COMPLETED)
        log = UsageLog.objects.filter(tenant=self.tenant, endpoint='sign-usb').latest('pk')
        self.assertTrue(log.success)
        self.assertEqual(log.signing_source, 'usb')
        self.assertEqual(log.user, self.user)

    def test_agent_page_requires_login(self):
        anon = Client()
        response = anon.get('/dashboard/agent/')
        self.assertEqual(response.status_code, 302)

    def test_agent_download_requires_login(self):
        anon = Client()
        response = anon.get('/dashboard/agent/download/')
        self.assertEqual(response.status_code, 302)

    def test_agent_download_returns_zip_for_active_tenant(self):
        response = self.client.get('/dashboard/agent/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertGreater(len(response.content), 500)
        import zipfile
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            names = archive.namelist()
        self.assertIn('ig-esign-agent/agent.py', names)
        self.assertIn('ig-esign-agent/portal.url', names)
        self.assertIn('ig-esign-agent/start-agent.bat', names)

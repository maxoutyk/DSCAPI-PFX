import base64

import fitz
from django.contrib.auth.models import User
from django.test import Client, TestCase
from rest_framework.test import APIClient

from accounts.models import DocumentType, MembershipRole, Tenant, TenantMembership, TenantStatus, UsageLog
from accounts.services import create_api_key, store_certificate
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

    def test_agent_version_endpoint_is_public(self):
        from .distribution import microsoft_store_agent_url, read_agent_version

        response = self.api.get('/api/agent/version/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['version'], read_agent_version())
        self.assertEqual(payload['microsoft_store_url'], microsoft_store_agent_url())
        self.assertNotIn('store_download_url', payload)
        self.assertNotIn('has_windows_installer', payload)

    def test_agent_heartbeat_and_usb_sign_job(self):
        if not self.has_pfx:
            self.skipTest('PFX cert not available locally')

        pairing = create_pairing_code(tenant=self.tenant, user=self.user)
        device, token = pair_device(code=pairing.code, machine_name='test-pc', agent_version='0.1.0')
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        heartbeat = self.api.post('/api/agent/heartbeat/', {'agent_version': '0.1.0'}, format='json')
        self.assertEqual(heartbeat.status_code, 200)
        self.assertIn('latest_agent_version', heartbeat.json())

        pdf = _pdf_with_anchor()
        job = prepare_usb_sign_job(tenant=self.tenant, user=self.user, pdf_data=pdf, device=device)
        fetch = self.api.get(
            f'/api/agent/jobs/{job.id}/',
            HTTP_X_SIGN_TOKEN=job.sign_token,
        )
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
            {
                'signed_pdf_base64': base64.b64encode(signed.signed_pdf_data).decode('ascii'),
                'sign_token': job.sign_token,
                'client_mac': 'aa-bb-cc-dd-ee-ff',
            },
            format='json',
            HTTP_USER_AGENT='IG-E-Sign-Agent/0.1',
        )
        self.assertEqual(complete.status_code, 200)

        job.refresh_from_db()
        self.assertEqual(job.status, UsbSignJobStatus.COMPLETED)
        log = UsageLog.objects.filter(tenant=self.tenant, endpoint='sign-usb').latest('pk')
        self.assertTrue(log.success)
        self.assertEqual(log.signing_source, 'usb')
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.client_mac, 'AA:BB:CC:DD:EE:FF')
        self.assertEqual(log.user_agent, 'IG-E-Sign-Agent/0.1')

    def test_complete_rejects_unrelated_signed_pdf(self):
        if not self.has_pfx:
            self.skipTest('PFX cert not available locally')

        pairing = create_pairing_code(tenant=self.tenant, user=self.user)
        device, token = pair_device(code=pairing.code, machine_name='test-pc', agent_version='0.1.0')
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        original = _pdf_with_anchor()
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), 'DIFFERENT INVOICE BODY')
        page.insert_text((72, 120), 'Authorised Signatory')
        other = doc.tobytes()
        doc.close()

        job = prepare_usb_sign_job(tenant=self.tenant, user=self.user, pdf_data=original, device=device)
        audit = SigningAuditMeta(endpoint='signpdf-pfx', user=self.user)
        signed_other = sign_pdf_for_tenant(
            tenant=self.tenant,
            pdf_data=other,
            password=self.pfx_password,
            cert_alias='emudratest',
            audit=audit,
        )
        complete = self.api.post(
            f'/api/agent/jobs/{job.id}/complete/',
            {
                'signed_pdf_base64': base64.b64encode(signed_other.signed_pdf_data).decode('ascii'),
                'sign_token': job.sign_token,
            },
            format='json',
        )
        self.assertEqual(complete.status_code, 400)
        job.refresh_from_db()
        self.assertEqual(job.status, UsbSignJobStatus.FAILED)
        self.assertIn('prepared document', job.error_message)

    def test_agent_job_requires_sign_token(self):
        pairing = create_pairing_code(tenant=self.tenant, user=self.user)
        device, token = pair_device(code=pairing.code, machine_name='test-pc', agent_version='0.1.0')
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        job = prepare_usb_sign_job(
            tenant=self.tenant,
            user=self.user,
            pdf_data=_pdf_with_anchor(),
            device=device,
        )
        denied = self.api.get(f'/api/agent/jobs/{job.id}/')
        self.assertEqual(denied.status_code, 400)

    def test_agent_fail_marks_job_failed(self):
        pairing = create_pairing_code(tenant=self.tenant, user=self.user)
        device, token = pair_device(code=pairing.code, machine_name='test-pc', agent_version='0.1.0')
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        job = prepare_usb_sign_job(
            tenant=self.tenant,
            user=self.user,
            pdf_data=_pdf_with_anchor(),
            device=device,
        )
        response = self.api.post(
            f'/api/agent/jobs/{job.id}/fail/',
            {
                'sign_token': job.sign_token,
                'error': 'Signing cancelled — token PIN was not entered.',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], UsbSignJobStatus.FAILED)
        job.refresh_from_db()
        self.assertEqual(job.status, UsbSignJobStatus.FAILED)
        self.assertEqual(job.error_message, 'Signing cancelled — token PIN was not entered.')
        self.assertEqual(job.sign_token, '')

        status = self.client.get(f'/dashboard/sign/usb/{job.id}/status/')
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()['status'], UsbSignJobStatus.FAILED)
        self.assertIn('Signing cancelled', status.json()['error'])

    def test_agent_page_requires_login(self):
        anon = Client()
        response = anon.get('/dashboard/agent/')
        self.assertEqual(response.status_code, 302)

    def test_agent_page_shows_microsoft_store_link(self):
        from .distribution import microsoft_store_agent_url

        response = self.client.get('/dashboard/agent/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, microsoft_store_agent_url())
        self.assertContains(response, 'Get from Microsoft Store')


class TenantUsbSignApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='api-usb@example.com', email='api-usb@example.com', password='pass')
        self.tenant = Tenant.objects.create(
            name='API USB Org',
            slug='api-usb-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=MembershipRole.OWNER,
            is_primary=True,
        )
        self.api_key, self.raw_api_key = create_api_key(self.tenant, 'usb-test')
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {self.raw_api_key}')

    def test_create_and_poll_usb_sign_job(self):
        pairing = create_pairing_code(tenant=self.tenant, user=self.user)
        device, _token = pair_device(code=pairing.code, machine_name='api-pc', agent_version='0.1.0')

        pdf_b64 = base64.b64encode(_pdf_with_anchor()).decode('ascii')
        create = self.api.post(
            '/api/sign/usb/',
            {'pdf_base64': pdf_b64, 'device_id': device.pk},
            format='json',
        )
        self.assertEqual(create.status_code, 201)
        body = create.json()
        self.assertEqual(body['status'], UsbSignJobStatus.PREPARED)
        self.assertIn('job_id', body)
        self.assertIn('sign_token', body)
        self.assertIn('agent_sign_url', body)

        job_id = body['job_id']
        detail = self.api.get(f'/api/sign/usb/{job_id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['status'], UsbSignJobStatus.PREPARED)
        self.assertNotIn('sign_token', detail.json())

        token_response = self.api.post(f'/api/sign/usb/{job_id}/agent-token/')
        self.assertEqual(token_response.status_code, 200)
        self.assertIn('sign_token', token_response.json())

    def test_create_requires_api_key(self):
        client = APIClient()
        pdf_b64 = base64.b64encode(_pdf_with_anchor()).decode('ascii')
        response = client.post(
            '/api/sign/usb/',
            {'pdf_base64': pdf_b64, 'device_id': 1},
            format='json',
        )
        self.assertIn(response.status_code, (401, 403))

    def test_create_requires_device_id(self):
        pdf_b64 = base64.b64encode(_pdf_with_anchor()).decode('ascii')
        response = self.api.post('/api/sign/usb/', {'pdf_base64': pdf_b64}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_download_completed_job(self):
        pairing = create_pairing_code(tenant=self.tenant, user=self.user)
        device, _token = pair_device(code=pairing.code, machine_name='api-pc', agent_version='0.1.0')
        pdf = _pdf_with_anchor()
        job = prepare_usb_sign_job(
            tenant=self.tenant,
            pdf_data=pdf,
            api_key=self.api_key,
            device=device,
        )
        job.status = UsbSignJobStatus.COMPLETED
        job.hash_after = 'abc123'
        from accounts.services import encrypt_pfx

        job.encrypted_pdf = encrypt_pfx(pdf)
        job.save()

        download = self.api.get(f'/api/sign/usb/{job.id}/download/')
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download['Content-Type'], 'application/pdf')
        self.assertEqual(download.content, pdf)

        as_json = self.api.get(f'/api/sign/usb/{job.id}/download/?format=json')
        self.assertEqual(as_json.status_code, 200)
        self.assertIn('signed_pdf_base64', as_json.json())

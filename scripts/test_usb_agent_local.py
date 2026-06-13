#!/usr/bin/env python3
"""
Local USB agent smoke test (no browser).

Terminal 1: python manage.py runserver 127.0.0.1:8000
Terminal 2: python scripts/test_usb_agent_local.py

Uses yogesh@incitegravity.com + active tenant. Override with TEST_USER_EMAIL env.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DSCApi.settings')

import django

django.setup()

import fitz
from django.contrib.auth.models import User

from accounts.models import TenantMembership, TenantStatus
from usb_agent.services import create_pairing_code, pair_device, prepare_usb_sign_job

API_BASE = os.environ.get('API_BASE', 'http://127.0.0.1:8000').rstrip('/')
AGENT_PORT = int(os.environ.get('USB_AGENT_LOCAL_PORT', '9765'))
EMAIL = os.environ.get('TEST_USER_EMAIL', 'yogesh@incitegravity.com')
PFX_PATH = os.environ.get('IG_AGENT_DEV_PFX_PATH', str(ROOT / 'certs' / 'e-Mudhra Sub CA.pfx'))
PFX_PASSWORD = os.environ.get('IG_AGENT_DEV_PFX_PASSWORD', 'emudhra')


def _pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), 'TAX INVOICE')
    page.insert_text((72, 120), 'Authorised Signatory')
    data = doc.tobytes()
    doc.close()
    return data


def main():
    print('Checking API…', API_BASE)
    try:
        urllib.request.urlopen(f'{API_BASE}/login/', timeout=3)
    except urllib.error.URLError as exc:
        sys.exit(f'Start runserver first: python manage.py runserver 127.0.0.1:8000\n  ({exc})')

    user = User.objects.filter(email=EMAIL).first()
    if not user:
        sys.exit(f'No user {EMAIL}. Register/login once or set TEST_USER_EMAIL.')
    membership = TenantMembership.objects.filter(user=user, is_primary=True).select_related('tenant').first()
    if not membership or membership.tenant.status != TenantStatus.ACTIVE:
        sys.exit('User needs an active tenant.')

    tenant = membership.tenant
    code = create_pairing_code(tenant=tenant, user=user)
    print(f'Pairing code: {code.code}')

    subprocess.run(
        [sys.executable, str(ROOT / 'desktop-agent' / 'agent.py'), 'pair', '--api-base', API_BASE, '--code', code.code],
        check=True,
    )

    env = os.environ.copy()
    env['IG_AGENT_DEV_PFX_PATH'] = PFX_PATH
    env['IG_AGENT_DEV_PFX_PASSWORD'] = PFX_PASSWORD
    agent_proc = subprocess.Popen(
        [sys.executable, str(ROOT / 'desktop-agent' / 'agent.py'), 'run', '--port', str(AGENT_PORT)],
        env=env,
    )
    time.sleep(1)

    try:
        health = urllib.request.urlopen(f'http://127.0.0.1:{AGENT_PORT}/health', timeout=3)
        print('Agent health:', health.read().decode())

        job = prepare_usb_sign_job(tenant=tenant, user=user, pdf_data=_pdf())
        print(f'Prepared job: {job.id}')

        req = urllib.request.Request(
            f'http://127.0.0.1:{AGENT_PORT}/sign',
            data=json.dumps({
                'job_id': str(job.id),
                'api_base': API_BASE,
                'sign_token': job.sign_token,
            }).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
        print('Agent sign result:', result)

        job.refresh_from_db()
        if job.status != 'completed':
            sys.exit(f'Expected completed, got {job.status}: {job.error_message}')
        print(f'SUCCESS signing_id={job.signing_event_id} endpoint=sign-usb')
    finally:
        agent_proc.terminate()
        agent_proc.wait(timeout=5)


if __name__ == '__main__':
    main()

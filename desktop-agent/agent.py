#!/usr/bin/env python3
"""
IG E-Sign desktop agent (development stub).

Production builds will add PKCS#11 USB token signing. This stub:
- exposes localhost /health and /sign for the portal bridge
- pairs with the cloud API using a one-time code
- fetches prepared jobs and completes them (dev mode: optional PFX signing)

Usage:
  python agent.py pair --api-base http://localhost --code 123456
  python agent.py run --api-base http://localhost --port 9765
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AGENT_VERSION = '0.1.0-dev'
CONFIG_PATH = Path.home() / '.ig-esign-agent' / 'config.json'


def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    return json.loads(CONFIG_PATH.read_text())


def save_config(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def api_request(method: str, url: str, payload: dict | None = None, token: str = '') -> dict:
    body = None
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if payload is not None:
        body = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(detail or exc.reason) from exc


def pair_agent(api_base: str, code: str):
    data = api_request(
        'POST',
        f'{api_base.rstrip("/")}/api/agent/pair/',
        {
            'code': code,
            'machine_name': platform.node(),
            'agent_version': AGENT_VERSION,
        },
    )
    config = load_config()
    config['api_base'] = api_base.rstrip('/')
    config['device_token'] = data['device_token']
    save_config(config)
    print(f"Paired with tenant {data.get('tenant')} (device {data.get('device_id')})")


def heartbeat(api_base: str, token: str):
    api_request(
        'POST',
        f'{api_base}/api/agent/heartbeat/',
        {'agent_version': AGENT_VERSION, 'token_present': False},
        token=token,
    )


def sign_job(api_base: str, token: str, job_id: str) -> dict:
    job = api_request('GET', f'{api_base}/api/agent/jobs/{job_id}/', token=token)
    pdf_data = base64.b64decode(job['pdf_base64'])

    dev_pfx = os.environ.get('IG_AGENT_DEV_PFX_PATH', '').strip()
    dev_password = os.environ.get('IG_AGENT_DEV_PFX_PASSWORD', '').strip()
    if dev_pfx and dev_password:
        signed_pdf_data = _sign_with_pfx(pdf_data, job['placement'], dev_pfx, dev_password)
    else:
        raise RuntimeError(
            'PKCS#11 signing is not implemented yet. '
            'Set IG_AGENT_DEV_PFX_PATH and IG_AGENT_DEV_PFX_PASSWORD for local development.',
        )

    signed_b64 = base64.b64encode(signed_pdf_data).decode('ascii')
    return api_request(
        'POST',
        f'{api_base}/api/agent/jobs/{job_id}/complete/',
        {'signed_pdf_base64': signed_b64},
        token=token,
    )


def _sign_with_pfx(pdf_data: bytes, placement: dict, pfx_path: str, password: str) -> bytes:
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DSCApi.settings')
    import django

    django.setup()

    from endesive import pdf as endesive_pdf
    from signPdf.pdf_signing import (
        build_signing_dict,
        get_cn_from_certificate,
        get_indian_time_str,
        load_pfx_credentials,
        sign_pdf_at_positions,
    )
    from dataclasses import replace

    from signPdf.signature_style import SignatureStyleConfig

    pfx_bytes = Path(pfx_path).read_bytes()
    private_key, certificate, additional_certs = load_pfx_credentials(pfx_bytes, password)
    style_data = placement.get('style', {})
    base_style = SignatureStyleConfig.from_settings()
    style = replace(
        base_style,
        anchor_text=style_data.get('anchor_text', base_style.anchor_text),
        font_size=style_data.get('font_size', base_style.font_size),
        box_min_width=style_data.get('box_min_width', base_style.box_min_width),
        box_height=style_data.get('box_height', base_style.box_height),
        box_right_padding=style_data.get('box_right_padding', base_style.box_right_padding),
        box_shift_right=style_data.get('box_shift_right', base_style.box_shift_right),
        box_gap_above_label=style_data.get('box_gap_above_label', base_style.box_gap_above_label),
        box_shift_down_fitz=style_data.get('box_shift_down_fitz', base_style.box_shift_down_fitz),
        box_page_margin=style_data.get('box_page_margin', base_style.box_page_margin),
        icon_display_width=style_data.get('icon_display_width', base_style.icon_display_width),
        icon_overlap_inset=style_data.get('icon_overlap_inset', base_style.icon_overlap_inset),
        icon_padding=style_data.get('icon_padding', base_style.icon_padding),
        is_custom=style_data.get('is_custom', False),
    )
    positions = placement['positions']
    indian_time_str, indian_time = get_indian_time_str()
    cn = get_cn_from_certificate(certificate)
    dct = build_signing_dict(cn, indian_time_str, indian_time, style=style)
    return sign_pdf_at_positions(
        pdf_data,
        positions,
        dct,
        lambda data, position_dct: endesive_pdf.cms.sign(
            data, position_dct, private_key, certificate, additional_certs, 'sha256',
        ),
        style=style,
    )


class AgentHandler(BaseHTTPRequestHandler):
    server_version = 'IGEsignAgent/0.1'

    def log_message(self, format, *args):
        return

    def _cors(self):
        origin = self.headers.get('Origin', '*')
        self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path != '/health':
            self.send_error(404)
            return
        payload = json.dumps({'ok': True, 'version': AGENT_VERSION}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path != '/sign':
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', '0'))
        body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        job_id = body.get('job_id')
        config = load_config()
        token = config.get('device_token', '')
        api_base = (body.get('api_base') or config.get('api_base') or '').rstrip('/')
        if not job_id or not token or not api_base:
            self._json(400, {'error': 'Agent is not paired or job_id missing.'})
            return
        try:
            result = sign_job(api_base, token, job_id)
            self._json(200, result)
        except Exception as exc:
            self._json(500, {'error': str(exc)})

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(body)


def run_server(port: int):
    config = load_config()
    api_base = config.get('api_base', '')
    token = config.get('device_token', '')
    if api_base and token:
        heartbeat(api_base, token)

        def loop():
            while True:
                try:
                    heartbeat(api_base, token)
                except Exception:
                    pass
                threading.Event().wait(45)

        threading.Thread(target=loop, daemon=True).start()

    server = ThreadingHTTPServer(('127.0.0.1', port), AgentHandler)
    print(f'IG E-Sign Agent listening on http://127.0.0.1:{port}')
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description='IG E-Sign USB agent (dev stub)')
    sub = parser.add_subparsers(dest='command', required=True)

    pair_parser = sub.add_parser('pair')
    pair_parser.add_argument('--api-base', required=True)
    pair_parser.add_argument('--code', required=True)

    run_parser = sub.add_parser('run')
    run_parser.add_argument('--port', type=int, default=9765)

    args = parser.parse_args()
    if args.command == 'pair':
        pair_agent(args.api_base, args.code)
    elif args.command == 'run':
        run_server(args.port)


if __name__ == '__main__':
    main()

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
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

def _read_version() -> str:
    if getattr(sys, 'frozen', False):
        candidates = (
            Path(getattr(sys, '_MEIPASS', '')) / 'VERSION',
            Path(sys.executable).parent / 'VERSION',
        )
    else:
        candidates = (Path(__file__).resolve().parent / 'VERSION',)
    for version_path in candidates:
        if version_path.is_file():
            return version_path.read_text().strip() or '0.1.0'
    return '0.1.0'


AGENT_VERSION = _read_version()
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


def token_present() -> bool:
    try:
        from pkcs11_signing import token_slot_present

        return token_slot_present()
    except Exception:
        return False


def heartbeat(api_base: str, token: str):
    api_request(
        'POST',
        f'{api_base}/api/agent/heartbeat/',
        {'agent_version': AGENT_VERSION, 'token_present': token_present()},
        token=token,
    )


def _origin_from_base(api_base: str) -> str:
    parsed = urllib.parse.urlparse((api_base or '').strip())
    if not parsed.scheme or not parsed.netloc:
        return ''
    return f'{parsed.scheme}://{parsed.netloc}'.rstrip('/')


def _allowed_cors_origins(config: dict, api_base: str = '') -> set[str]:
    origins: set[str] = set()
    for base in (config.get('api_base', ''), api_base):
        origin = _origin_from_base(base)
        if origin:
            origins.add(origin)
    for item in config.get('allowed_origins', []):
        normalized = str(item).strip().rstrip('/')
        if normalized:
            origins.add(normalized)
    return origins


def sign_job(api_base: str, token: str, job_id: str, sign_token: str) -> dict:
    token_qs = urllib.parse.quote(sign_token, safe='')
    job = api_request(
        'GET',
        f'{api_base}/api/agent/jobs/{job_id}/?sign_token={token_qs}',
        token=token,
    )
    pdf_data = base64.b64decode(job['pdf_base64'])

    dev_pfx = os.environ.get('IG_AGENT_DEV_PFX_PATH', '').strip()
    dev_password = os.environ.get('IG_AGENT_DEV_PFX_PASSWORD', '').strip()
    signed_pdf_data = None
    sign_errors: list[str] = []

    if not (dev_pfx and dev_password):
        try:
            from signing import Pkcs11NotAvailable, sign_pdf_with_pkcs11

            signed_pdf_data = sign_pdf_with_pkcs11(pdf_data, job['placement'])
        except Pkcs11NotAvailable as exc:
            sign_errors.append(str(exc))
        except Exception as exc:
            sign_errors.append(f'USB token signing failed: {exc}')
    if signed_pdf_data is None:
        if dev_pfx and dev_password:
            from signing import sign_pdf_with_pfx

            signed_pdf_data = sign_pdf_with_pfx(pdf_data, job['placement'], dev_pfx, dev_password)
        else:
            raise RuntimeError(sign_errors[0] if sign_errors else 'USB token signing is unavailable.')

    try:
        signed_b64 = base64.b64encode(signed_pdf_data).decode('ascii')
        return api_request(
            'POST',
            f'{api_base}/api/agent/jobs/{job_id}/complete/',
            {'signed_pdf_base64': signed_b64, 'sign_token': sign_token},
            token=token,
        )
    finally:
        try:
            from pkcs11_signing import clear_session_pin

            clear_session_pin()
        except Exception:
            pass


class AgentHandler(BaseHTTPRequestHandler):
    server_version = 'IGEsignAgent/0.1'

    def log_message(self, format, *args):
        return

    def _resolve_cors_origin(self, api_base: str = '') -> str | None:
        request_origin = (self.headers.get('Origin') or '').strip().rstrip('/')
        if not request_origin:
            return None
        config = load_config()
        if request_origin in _allowed_cors_origins(config, api_base):
            return request_origin
        return None

    def _cors(self, allowed_origin: str | None = None):
        if allowed_origin:
            self.send_header('Access-Control-Allow-Origin', allowed_origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        config = load_config()
        api_base = config.get('api_base', '')
        allowed = self._resolve_cors_origin(api_base)
        if self.headers.get('Origin') and not allowed:
            self.send_error(403)
            return
        self.send_response(204)
        self._cors(allowed)
        self.end_headers()

    def do_GET(self):
        if self.path != '/health':
            self.send_error(404)
            return
        config = load_config()
        allowed = self._resolve_cors_origin(config.get('api_base', ''))
        if self.headers.get('Origin') and not allowed:
            self.send_error(403)
            return
        payload = json.dumps(
            {'ok': True, 'version': AGENT_VERSION, 'token_present': token_present()},
        ).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors(allowed)
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path != '/sign':
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', '0'))
        body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        job_id = body.get('job_id')
        sign_token = (body.get('sign_token') or '').strip()
        config = load_config()
        token = config.get('device_token', '')
        api_base = (body.get('api_base') or config.get('api_base') or '').rstrip('/')
        allowed = self._resolve_cors_origin(api_base)
        if self.headers.get('Origin') and not allowed:
            self.send_error(403)
            return
        if not job_id or not token or not api_base or not sign_token:
            self._json(400, {'error': 'Agent is not paired or job_id/sign_token missing.'}, allowed)
            return
        try:
            result = sign_job(api_base, token, job_id, sign_token)
            self._json(200, result, allowed)
        except Exception as exc:
            self._json(500, {'error': str(exc)}, allowed)

    def _json(self, status: int, payload: dict, allowed_origin: str | None = None):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._cors(allowed_origin)
        self.end_headers()
        self.wfile.write(body)


def run_server(port: int):
    config = load_config()
    api_base = config.get('api_base', '')
    token = config.get('device_token', '')
    if not token:
        print('Agent is not paired yet. Run "Pair Agent.bat" and enter a code from the portal.')
    elif api_base and token:
        try:
            heartbeat(api_base, token)
            print(f'Connected to portal at {api_base}')
        except Exception as exc:
            print(f'Warning: could not reach portal ({exc}). Agent will still run locally.')

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
    print('Keep this window open while signing from the portal.')
    server.serve_forever()


def main():
    if getattr(sys, 'frozen', False) and len(sys.argv) == 1:
        sys.argv.append('run')

    parser = argparse.ArgumentParser(description='IG E-Sign USB agent')
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

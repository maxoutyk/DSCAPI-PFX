"""Structured API documentation catalog for the public docs UI."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_api_docs_catalog(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip('/')

    catalog = {
        'base_url': base,
        'services': [
            {
                'id': 'introduction',
                'title': 'Introduction',
                'items': [
                    {
                        'id': 'overview',
                        'title': 'Overview',
                        'kind': 'guide',
                        'description': (
                            'IG E-Sign provides REST APIs for PDF signing (PFX and Class 3 DSC '
                            'USB tokens) and GST services — GSTIN lookups, E-way bill print, and '
                            'e-invoice (IRN) print. All tenant APIs use a single Bearer API key '
                            'issued from your dashboard.'
                        ),
                        'sections': [
                            {
                                'title': 'Base URL',
                                'body': f'`{base}`',
                            },
                            {
                                'title': 'Content type',
                                'body': 'Send `Content-Type: application/json` on POST requests.',
                            },
                            {
                                'title': 'Requirements',
                                'bullets': [
                                    'Account status must be **Active** (admin-approved).',
                                    'Complete your **company profile** before GST lookup APIs.',
                                    'Monthly quotas apply per tenant across signing, USB signing, and GST services.',
                                ],
                            },
                        ],
                    },
                    {
                        'id': 'authentication',
                        'title': 'Authentication',
                        'kind': 'guide',
                        'description': (
                            'Create an API key under **Dashboard → API Keys**. '
                            'Pass it on every request using the Bearer scheme. Keys are shown '
                            'once at creation — store them securely.'
                        ),
                        'sections': [
                            {
                                'title': 'Header',
                                'body': '`Authorization: Bearer dsc_live_<your-secret-key>`',
                            },
                            {
                                'title': 'Security notes',
                                'bullets': [
                                    'Use API keys only from server-side integrations.',
                                    'Never embed keys in frontend JavaScript or mobile apps.',
                                    'Revoke compromised keys immediately from the portal.',
                                ],
                            },
                            {
                                'title': 'Example request',
                                'code': f'''curl -s "{base}/api/gst/gstin/search/" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"''',
                                'code_lang': 'curl',
                            },
                        ],
                    },
                ],
            },
            {
                'id': 'signing',
                'title': 'PDF Signing',
                'items': [
                    _sign_pdf_pfx(base),
                ],
            },
            {
                'id': 'usb',
                'title': 'DSC Signing (Class 3 USB Token)',
                'items': [
                    _usb_overview(base),
                    _usb_create_job(base),
                    _usb_local_agent(base),
                    _usb_local_agent_health(base),
                    _usb_poll_status(base),
                    _usb_download(base),
                ],
            },
            {
                'id': 'gst',
                'title': 'GST Services',
                'items': [
                    _gst_gstin_search(base),
                    _gst_preference(base),
                    _gst_return_status(base),
                    _gst_eway_print(base),
                    _gst_irn_print(base),
                ],
            },
            {
                'id': 'usage',
                'title': 'Usage Reports',
                'items': [
                    _usage_report_overall(base),
                    _usage_report_customer(base),
                ],
            },
        ],
    }
    return catalog


def flatten_catalog_items(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for service in catalog['services']:
        for item in service['items']:
            row = deepcopy(item)
            row['service_id'] = service['id']
            row['service_title'] = service['title']
            items.append(row)
    return items


def get_catalog_item(catalog: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for item in flatten_catalog_items(catalog):
        if item['id'] == item_id:
            return item
    return None


def build_service_catalog(base_url: str, service_ids: list[str]) -> dict[str, Any]:
    """Return a catalog slice containing only the requested services."""
    full = build_api_docs_catalog(base_url)
    allowed = set(service_ids)
    services = [service for service in full['services'] if service['id'] in allowed]
    return {'base_url': full['base_url'], 'services': services}


def personalize_catalog_defaults(
    catalog: dict[str, Any],
    *,
    gstin: str = '',
    fy: str = '2024-25',
) -> dict[str, Any]:
    """Attach portal defaults used by the try-it form and sample values."""
    personalized = deepcopy(catalog)
    personalized['defaults'] = {
        'gstin': gstin,
        'fy': fy,
        'type': 'R1',
    }
    return personalized


def _sign_pdf_pfx(base: str) -> dict[str, Any]:
    return {
        'id': 'sign-pdf-pfx',
        'title': 'Sign a PDF',
        'kind': 'endpoint',
        'method': 'POST',
        'path': '/api/signpdf-pfx',
        'description': (
            'Sign a PDF using an inline PFX or a certificate saved in your portal. '
            'Provide exactly one of `pfx_base64` or `cert_alias`. Optional `signature_style` '
            'selects a named placement style from your dashboard.'
        ),
        'parameters': [
            {'name': 'pdf_base64', 'type': 'string', 'required': True, 'description': 'Base64-encoded PDF (max 10 MB).'},
            {'name': 'password', 'type': 'string', 'required': True, 'description': 'PFX password. Not stored server-side.'},
            {'name': 'pfx_base64', 'type': 'string', 'required': False, 'description': 'Inline PFX file (base64). Use this or `cert_alias`.'},
            {'name': 'cert_alias', 'type': 'string', 'required': False, 'description': 'Saved certificate alias from the portal.'},
            {'name': 'signature_style', 'type': 'string', 'required': False, 'description': 'Optional enabled style name (e.g. `Invoice`).'},
        ],
        'responses': [
            {'status': 200, 'description': 'PDF signed successfully.'},
            {'status': 400, 'description': 'Validation error, bad password, or anchor text not found.'},
            {'status': 401, 'description': 'Missing or invalid API key.'},
            {'status': 403, 'description': 'Account not active.'},
            {'status': 429, 'description': 'Monthly quota or rate limit exceeded.'},
        ],
        'request_json': '''{
  "pdf_base64": "<base64-encoded PDF>",
  "password": "your-pfx-password",
  "cert_alias": "company-dsc",
  "signature_style": "Invoice"
}''',
        'curl': f'''curl -X POST "{base}/api/signpdf-pfx" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "pdf_base64": "...",
    "cert_alias": "company-dsc",
    "password": "pfx-password"
  }}' ''',
        'response_success_json': '''{
  "message": "PDF signed successfully using PFX.",
  "signed_pdf_base64": "...",
  "signing_id": 42,
  "hash_before_prefix": "a1b2c3d4",
  "hash_after_prefix": "e5f6g7h8"
}''',
        'response_error_json': '''{
  "error": "No position found for anchor text: 'Authorised Signatory'"
}''',
    }


def _usb_overview(base: str) -> dict[str, Any]:
    return {
        'id': 'usb-overview',
        'title': 'How USB DSC signing works',
        'kind': 'guide',
        'description': (
            'Sign with a Class 3 DSC (Digital Signature Certificate) on a USB token — '
            'eMudhra, Capricorn, and similar providers. The private key never leaves the '
            'USB device; IG E-Sign prepares the PDF in the cloud and the IG E-Sign Agent '
            'on Windows signs locally via PKCS#11.'
        ),
        'sections': [
            {
                'title': 'Signing flow',
                'bullets': [
                    'Step 1 — Your **server** calls POST /api/sign/usb/ with the PDF and target device_id.',
                    'Step 2 — On the signing PC, trigger the local agent (POST http://127.0.0.1:9765/sign) with job_id and sign_token.',
                    'Step 3 — Your **server** polls GET /api/sign/usb/{job_id}/ every 2–5 seconds until status is completed, failed, or expired.',
                    'Step 4 — Your **server** downloads the signed PDF (GET /api/sign/usb/{job_id}/download/) or uses ?include_pdf=1 on the poll endpoint.',
                ],
            },
            {
                'title': 'Server vs browser (ERP integrations)',
                'bullets': [
                    'Cloud API calls (create, poll, download) must run **server-side** with your API key — they do not send CORS headers for third-party origins such as Dynamics or Business Central.',
                    'Only Step 2 runs in the browser on the signing PC (or via a local script/service on that machine).',
                    'Never embed dsc_live_… API keys in frontend JavaScript.',
                ],
            },
            {
                'title': 'One-time setup',
                'bullets': [
                    'Create an API key and use Authorization: Bearer dsc_live_… on all cloud API calls.',
                    'On the Windows PC with the Class 3 USB token: Dashboard → USB Agent → download and pair the agent.',
                    'Keep IG E-Sign Agent running in the system tray while signing.',
                    'Note the device_id for each paired machine from the USB Agent page.',
                    'Jobs expire after 15 minutes if not completed. agents_online counts devices with a heartbeat in the last ~90 seconds.',
                ],
            },
            {
                'title': 'Local agent CORS (third-party web apps)',
                'body': (
                    'The agent accepts browser calls only from allowed Origins: the paired portal URL '
                    f'(`{base}`) plus extra entries configured in the agent app '
                    '(**Allowed browser origins**) or via CLI: '
                    '`agent.py origins add https://businesscentral.dynamics.com`. '
                    'POST /sign requires an `Origin` header. Changes apply immediately without restart.'
                ),
            },
        ],
    }


def _usb_create_job(base: str) -> dict[str, Any]:
    return {
        'id': 'usb-create-job',
        'title': 'Create sign job',
        'kind': 'endpoint',
        'method': 'POST',
        'path': '/api/sign/usb/',
        'description': (
            'Step 1 — Prepare a signing job for a paired Windows agent. Use this when the '
            'private key stays on a Class 3 DSC USB token. Returns a job_id and one-time '
            'sign_token for the local agent.'
        ),
        'parameters': [
            {'name': 'pdf_base64', 'type': 'string', 'required': True, 'description': 'Base64-encoded PDF (max 10 MB).'},
            {'name': 'device_id', 'type': 'integer', 'required': True, 'description': 'Paired agent device ID from the USB Agent page.'},
            {'name': 'signature_style', 'type': 'string', 'required': False, 'description': 'Optional enabled style name.'},
        ],
        'responses': [
            {'status': 201, 'description': 'Job prepared; trigger the local agent next.'},
            {'status': 400, 'description': 'Invalid PDF, anchor not found, unknown device_id, bad signature_style, or quota exceeded.'},
            {'status': 401, 'description': 'Missing or invalid API key.'},
            {'status': 403, 'description': 'Account not active.'},
            {'status': 429, 'description': 'Rate limit exceeded.'},
        ],
        'request_json': '''{
  "pdf_base64": "<base64-encoded PDF>",
  "device_id": 1,
  "signature_style": "Invoice"
}''',
        'curl': f'''curl -X POST "{base}/api/sign/usb/" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "pdf_base64": "...",
    "device_id": 1
  }}' ''',
        'response_success_json': '''{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "status": "prepared",
  "expires_at": "2026-06-13T12:30:00+00:00",
  "signing_id": null,
  "hash_before_prefix": "a1b2c3d4",
  "hash_after_prefix": "",
  "error": "",
  "device_id": 1,
  "document_type": "tax_invoice",
  "sign_token": "xY7…",
  "message": "USB sign job prepared. Trigger the desktop agent…",
  "agent_sign_url": "http://127.0.0.1:9765/sign",
  "agents_online": 1
}''',
        'response_error_json': '''{
  "device_id": ["Agent device not found for this tenant."]
}''',
    }


def _usb_poll_status(base: str) -> dict[str, Any]:
    return {
        'id': 'usb-poll-status',
        'title': 'Poll job status',
        'kind': 'endpoint',
        'method': 'GET',
        'path': '/api/sign/usb/{job_id}/',
        'description': (
            'Step 3 — Poll every 2–5 seconds after triggering the local agent until status '
            'is terminal (`completed`, `failed`, or `expired`). Call from your server, not '
            'from a browser on an ERP page. While `prepared`, the response includes `sign_token` '
            '(cleared after completion). There is no separate in-progress status — the agent '
            'signing window still shows `prepared`.'
        ),
        'parameters': [
            {'name': 'job_id', 'type': 'uuid', 'required': True, 'description': 'Job ID from the create response (path parameter).'},
            {'name': 'include_pdf', 'type': 'integer', 'required': False, 'description': 'Set to `1` to add `signed_pdf_base64` when status is `completed`.'},
        ],
        'responses': [
            {'status': 200, 'description': 'Current job status (see status values below).'},
            {'status': 404, 'description': 'Unknown job ID for this tenant.'},
        ],
        'curl': f'''curl "{base}/api/sign/usb/JOB_ID/" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"''',
        'response_success_json': '''{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "status": "completed",
  "expires_at": "2026-06-13T12:30:00+00:00",
  "signing_id": 42,
  "hash_before_prefix": "a1b2c3d4",
  "hash_after_prefix": "e5f6g7h8",
  "error": "",
  "device_id": 1,
  "document_type": "tax_invoice"
}''',
        'response_error_json': '''{
  "error": "Signing job not found."
}''',
    }


def _usb_download(base: str) -> dict[str, Any]:
    return {
        'id': 'usb-download',
        'title': 'Download signed PDF',
        'kind': 'endpoint',
        'method': 'GET',
        'path': '/api/sign/usb/{job_id}/download/',
        'description': (
            'Step 4 — Download the signed PDF when poll status is `completed`. '
            'Default response is a binary PDF file. Use `?format=json` for a JSON body with '
            '`signed_pdf_base64` (recommended for ERP server integrations). Server-side only.'
        ),
        'parameters': [
            {'name': 'job_id', 'type': 'uuid', 'required': True, 'description': 'Completed job ID (path parameter).'},
            {'name': 'format', 'type': 'string', 'required': False, 'description': 'Set to `json` for JSON with `signed_pdf_base64` instead of a file download.'},
        ],
        'responses': [
            {'status': 200, 'description': '`application/pdf` attachment, or JSON when `format=json`.'},
            {'status': 404, 'description': 'Unknown job ID or signed PDF no longer available.'},
            {'status': 409, 'description': 'Job status is not `completed` yet.'},
        ],
        'curl': f'''curl -o signed.pdf "{base}/api/sign/usb/JOB_ID/download/" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"

curl "{base}/api/sign/usb/JOB_ID/download/?format=json" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"''',
        'response_success_json': '''{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "signed_pdf_base64": "JVBERi0xLjQKJ...",
  "signing_id": 42,
  "hash_after_prefix": "e5f6g7h8"
}''',
        'response_error_json': '''{
  "error": "Job is not completed (status=prepared)."
}''',
    }


def _usb_local_agent(base: str) -> dict[str, Any]:
    origin = base.rstrip('/')
    return {
        'id': 'usb-local-agent',
        'title': 'Trigger local agent',
        'kind': 'endpoint',
        'method': 'POST',
        'path': 'http://127.0.0.1:9765/sign',
        'description': (
            'Step 2 — Run on the Windows PC with the Class 3 DSC USB token plugged in. '
            'The agent fetches the prepared job from the cloud, prompts for the token PIN, '
            'signs via PKCS#11, and uploads the signed PDF. This call is **synchronous** — '
            'the HTTP response is returned only after signing finishes or fails (often 10–30+ seconds). '
            'Send JSON with `job_id` and `sign_token` only — not your API key. The portal URL '
            'comes from agent pairing (`api_base` in local config). '
            '**HTTP only** (`http://127.0.0.1:9765`, not HTTPS). '
            'All responses are JSON with an `error` field on failure.'
        ),
        'parameters': [
            {
                'name': 'Origin',
                'type': 'header',
                'required': True,
                'description': (
                    'Required on every POST /sign request (browser and curl). Must match the paired '
                    f'portal origin (`{origin}`) or an entry in agent `allowed_origins`.'
                ),
            },
            {
                'name': 'Content-Type',
                'type': 'header',
                'required': True,
                'description': 'Must be `application/json`.',
            },
            {'name': 'job_id', 'type': 'uuid', 'required': True, 'description': 'Job ID from create/poll response.'},
            {'name': 'sign_token', 'type': 'string', 'required': True, 'description': 'One-time token from create/poll while status is `prepared`.'},
        ],
        'responses': [
            {
                'status': 200,
                'description': (
                    'Signing finished and the signed PDF was uploaded. Body is the cloud '
                    '`POST /api/agent/jobs/{job_id}/complete/` response.'
                ),
            },
            {
                'status': 400,
                'description': '`{"error": "Agent is not paired or job_id/sign_token missing."}` — empty body fields, or agent not paired (`device_token` / `api_base` missing in config).',
            },
            {
                'status': 403,
                'description': (
                    '`{"error": "Origin header is required for local signing."}` when `Origin` is omitted. '
                    'Or `{"error": "Origin is not allowed for this agent."}` when the origin is not in the allowlist. '
                    'Browsers also send an `OPTIONS` preflight first; a disallowed origin returns **403** with an empty body on preflight.'
                ),
            },
            {
                'status': 404,
                'description': 'Wrong path (not `/sign`) — plain HTML error page, not JSON.',
            },
            {
                'status': 500,
                'description': (
                    '`{"error": "<message>"}` — PKCS#11 / PIN cancelled / USB token errors, cloud job fetch or '
                    'upload failures, PDF verification rejection, or quota errors. The `error` string may be '
                    'plain text or a JSON blob from the cloud API. If the device token was revoked, the agent '
                    'clears local pairing and must be re-paired.'
                ),
            },
        ],
        'request_json': '''{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "sign_token": "xY7…"
}''',
        'curl': f'''curl -X POST "http://127.0.0.1:9765/sign" \\
  -H "Content-Type: application/json" \\
  -H "Origin: {origin}" \\
  -d '{{
    "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
    "sign_token": "xY7…"
  }}' ''',
        'response_success_json': '''{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "signing_id": 42,
  "hash_after": "e5f6g7h8a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef01234567"
}''',
        'response_error_json': '''{
  "error": "Origin header is required for local signing."
}''',
    }


def _usb_local_agent_health(base: str) -> dict[str, Any]:
    origin = base.rstrip('/')
    return {
        'id': 'usb-local-agent-health',
        'title': 'Local agent health',
        'kind': 'endpoint',
        'method': 'GET',
        'path': 'http://127.0.0.1:9765/health',
        'description': (
            'Optional check that the IG E-Sign Agent is running on the signing PC before calling '
            'POST /sign. `Origin` is optional for curl; browsers should send an allowed `Origin` '
            'so CORS succeeds. Does not perform signing.'
        ),
        'parameters': [
            {
                'name': 'Origin',
                'type': 'header',
                'required': False,
                'description': (
                    'If present, must be allowed (paired portal URL or `allowed_origins`). '
                    'If omitted, the request still succeeds when the agent is running.'
                ),
            },
        ],
        'responses': [
            {'status': 200, 'description': 'Agent is listening.'},
            {
                'status': 403,
                'description': 'Origin header present but not allowed (browser CORS failure).',
            },
            {'status': 404, 'description': 'Wrong path (not `/health`).'},
        ],
        'curl': f'''curl "http://127.0.0.1:9765/health" \\
  -H "Origin: {origin}"''',
        'response_success_json': '''{
  "ok": true,
  "version": "0.1.0",
  "token_present": true,
  "portal_paired": true,
  "portal_connected": true,
  "token_count": 1,
  "selected_token_display": "eMudhra — DS Example"
}''',
        'response_error_json': '''<!DOCTYPE HTML>
<html><head><title>Error 403 Forbidden</title></head>…''',
    }


def _gst_gstin_search(base: str) -> dict[str, Any]:
    return {
        'id': 'gst-gstin-search',
        'title': 'Get GSTIN details',
        'kind': 'endpoint',
        'method': 'GET',
        'path': '/api/gst/gstin/search/',
        'description': (
            'Look up taxpayer details for any valid GSTIN within your monthly quota. Requires a '
            'complete company profile. Omit `gstin` to use the GSTIN saved on your profile.'
        ),
        'parameters': [
            {'name': 'gstin', 'type': 'string', 'required': False, 'description': '15-character GSTIN to look up (defaults to profile GSTIN).'},
        ],
        'responses': [
            {'status': 200, 'description': 'GSTIN details returned from partner service.'},
            {'status': 403, 'description': 'Profile incomplete, NIC portal credentials missing, or account not active.'},
            {'status': 429, 'description': 'Monthly quota exceeded.'},
        ],
        'curl': f'''curl "{base}/api/gst/gstin/search/" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"''',
        'response_success_json': '''{
  "gstin": "33AAUPP8709M3ZS",
  "data": {
    "lgnm": "Example Traders Pvt Ltd",
    "sts": "Active"
  }
}''',
        'response_error_json': '''{
  "error": "Complete your company profile before using GST services."
}''',
    }


def _gst_preference(base: str) -> dict[str, Any]:
    return {
        'id': 'gst-preference',
        'title': 'Get preference',
        'kind': 'endpoint',
        'method': 'GET',
        'path': '/api/gst/preference/',
        'description': 'Fetch taxpayer preferences for a financial year.',
        'parameters': [
            {'name': 'fy', 'type': 'string', 'required': True, 'description': 'Financial year, e.g. `2024-25`.'},
            {'name': 'gstin', 'type': 'string', 'required': False, 'description': 'GSTIN to query (defaults to profile GSTIN).'},
        ],
        'responses': [
            {'status': 200, 'description': 'Preference data returned.'},
            {'status': 400, 'description': 'Invalid financial year format.'},
        ],
        'curl': f'''curl "{base}/api/gst/preference/?fy=2024-25" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"''',
        'response_success_json': '''{
  "gstin": "33AAUPP8709M3ZS",
  "fy": "2024-25",
  "data": {}
}''',
        'response_error_json': '''{
  "fy": ["Financial year must look like 2024-25."]
}''',
    }


def _gst_return_status(base: str) -> dict[str, Any]:
    return {
        'id': 'gst-return-status',
        'title': 'View return status',
        'kind': 'endpoint',
        'method': 'GET',
        'path': '/api/gst/returns/',
        'description': (
            'Check GSTR filing status for a financial year. Optional `type` filter: '
            '`R1`, `R3B`, or `R9`.'
        ),
        'parameters': [
            {'name': 'fy', 'type': 'string', 'required': True, 'description': 'Financial year, e.g. `2024-25`.'},
            {'name': 'type', 'type': 'string', 'required': False, 'description': 'Return type: `R1`, `R3B`, or `R9`.'},
            {'name': 'gstin', 'type': 'string', 'required': False, 'description': 'GSTIN to query (defaults to profile GSTIN).'},
        ],
        'responses': [
            {'status': 200, 'description': 'Return status data.'},
            {'status': 400, 'description': 'Invalid parameters or client IP unavailable.'},
        ],
        'curl': f'''curl "{base}/api/gst/returns/?fy=2024-25&type=R1" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"''',
        'response_success_json': '''{
  "gstin": "33AAUPP8709M3ZS",
  "fy": "2024-25",
  "type": "R1",
  "data": {}
}''',
        'response_error_json': '''{
  "error": "Client IP could not be determined for return status lookup."
}''',
    }


def _gst_eway_print(base: str) -> dict[str, Any]:
    return {
        'id': 'gst-eway-print',
        'title': 'Print E-WAY bill',
        'kind': 'endpoint',
        'method': 'GET',
        'path': '/api/gst/eway/print/',
        'description': (
            'Download the detailed E-WAY bill PDF for a 12-digit e-way bill number. '
            'Uses GSTIN and NIC portal credentials from your company profile by default. '
            'For API-only integrations, you may pass `gstin`, `nicUsername`, and `nicPassword` '
            'per request instead of saving them on the profile (POST recommended for passwords). '
            'Returns `application/pdf` by default; use `?format=json` for `pdf_base64`.'
        ),
        'parameters': [
            {'name': 'ewbNumber', 'type': 'string', 'required': True, 'description': '12-digit E-WAY bill number.'},
            {'name': 'gstin', 'type': 'string', 'required': False, 'description': 'GSTIN for the print request (defaults to profile GSTIN).'},
            {'name': 'nicUsername', 'type': 'string', 'required': False, 'description': 'NIC portal username (API only; must be sent with nicPassword).'},
            {'name': 'nicPassword', 'type': 'string', 'required': False, 'description': 'NIC portal password (API only; must be sent with nicUsername).'},
            {'name': 'format', 'type': 'string', 'required': False, 'description': 'Set to `json` for base64 JSON instead of a PDF file.'},
        ],
        'responses': [
            {'status': 200, 'description': 'PDF file or JSON with `pdf_base64`.'},
            {'status': 400, 'description': 'Invalid e-way bill number.'},
            {'status': 403, 'description': 'Profile incomplete, NIC portal credentials missing, or account not active.'},
            {'status': 429, 'description': 'Monthly quota exceeded.'},
            {'status': 503, 'description': 'Partner credentials not configured on the server.'},
        ],
        'curl': f'''curl -o eway.pdf "{base}/api/gst/eway/print/?ewbNumber=123456789012" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"

curl -X POST "{base}/api/gst/eway/print/" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{"ewbNumber":"123456789012","gstin":"33AAUPP8709M3ZS","nicUsername":"NIC_USER","nicPassword":"NIC_PASS","format":"json"}}'
''',
        'response_success_json': '''{
  "gstin": "33AAUPP8709M3ZS",
  "ewb_number": "123456789012",
  "filename": "eway-123456789012.pdf",
  "content_type": "application/pdf",
  "pdf_base64": "JVBERi0xLjQKJ..."
}''',
        'response_error_json': '''{
  "ewbNumber": ["E-way bill number must be a 12-digit number."]
}''',
    }


def _gst_irn_print(base: str) -> dict[str, Any]:
    return {
        'id': 'gst-irn-print',
        'title': 'Print e-invoice (IRN)',
        'kind': 'endpoint',
        'method': 'GET',
        'path': '/api/gst/einvoice/print/',
        'description': (
            'Download the e-invoice PDF for a 64-character Invoice Reference Number (IRN). '
            'Uses GSTIN and NIC portal credentials from your company profile by default. '
            'For API-only integrations, you may pass `gstin`, `nicUsername`, and `nicPassword` '
            'per request instead of saving them on the profile (POST recommended for passwords). '
            'Returns `application/pdf` by default; use `?format=json` for `pdf_base64`.'
        ),
        'parameters': [
            {'name': 'irn', 'type': 'string', 'required': True, 'description': '64-character hexadecimal IRN.'},
            {'name': 'gstin', 'type': 'string', 'required': False, 'description': 'GSTIN for the print request (defaults to profile GSTIN).'},
            {'name': 'nicUsername', 'type': 'string', 'required': False, 'description': 'NIC portal username (API only; must be sent with nicPassword).'},
            {'name': 'nicPassword', 'type': 'string', 'required': False, 'description': 'NIC portal password (API only; must be sent with nicUsername).'},
            {'name': 'format', 'type': 'string', 'required': False, 'description': 'Set to `json` for base64 JSON instead of a PDF file.'},
        ],
        'responses': [
            {'status': 200, 'description': 'PDF file or JSON with `pdf_base64`.'},
            {'status': 400, 'description': 'Invalid IRN.'},
            {'status': 403, 'description': 'Profile incomplete, NIC portal credentials missing, or account not active.'},
            {'status': 429, 'description': 'Monthly quota exceeded.'},
            {'status': 503, 'description': 'Partner credentials not configured on the server.'},
        ],
        'curl': f'''curl -o einvoice.pdf "{base}/api/gst/einvoice/print/?irn=IRN_HEX_64_CHARS" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"

curl -X POST "{base}/api/gst/einvoice/print/" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{"irn":"IRN_HEX_64_CHARS","gstin":"33AAUPP8709M3ZS","nicUsername":"NIC_USER","nicPassword":"NIC_PASS","format":"json"}}'
''',
        'response_success_json': '''{
  "gstin": "33AAUPP8709M3ZS",
  "irn": "2d4cacc69309dcb5b07c064ba6f88237d3eab6f171e3e95da8d91a0e93702c2f",
  "filename": "einvoice-2d4cacc6.pdf",
  "content_type": "application/pdf",
  "pdf_base64": "JVBERi0xLjQKJ..."
}''',
        'response_error_json': '''{
  "irn": ["IRN must be a 64-character hexadecimal string."]
}''',
    }


def _usage_report_overall(base: str) -> dict[str, Any]:
    return {
        'id': 'usage-report-overall',
        'title': 'Download usage report (overall)',
        'kind': 'endpoint',
        'method': 'GET',
        'path': '/api/usage/report/',
        'description': (
            'Download a branded usage report for your organization for a calendar month. '
            'Includes daily charts, customer breakdown, and API key attribution. '
            'Use `export=json` for structured data instead of a file download.'
        ),
        'parameters': [
            {'name': 'period', 'type': 'string', 'required': False, 'description': 'Calendar month as `YYYY-MM` (defaults to current month).'},
            {'name': 'scope', 'type': 'string', 'required': False, 'description': '`overall` (default) or `customer`.'},
            {'name': 'export', 'type': 'string', 'required': False, 'description': '`pdf` (default), `csv`, or `json`.'},
        ],
        'responses': [
            {'status': 200, 'description': 'PDF/CSV file attachment or JSON summary.'},
            {'status': 403, 'description': 'Account not active.'},
            {'status': 404, 'description': 'Customer not found when `scope=customer`.'},
        ],
        'curl': f'''curl -o usage-report.pdf "{base}/api/usage/report/?export=pdf&period=2026-06" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"

curl "{base}/api/usage/report/?export=json&period=2026-06" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"''',
        'response_success_json': '''{
  "organization": "Acme Pvt Ltd",
  "period": "2026-06",
  "period_start": "2026-06-01",
  "period_end": "2026-06-30",
  "scope": "overall",
  "total_usage": 42,
  "total_signing": 30,
  "total_gst": 12,
  "quota_used": 42,
  "monthly_quota": 100,
  "daily": [
    {"date": "2026-06-01", "signing": 2, "gst": 0, "total": 2}
  ],
  "customer_groups": [
    {"customer_label": "Portal", "bucket": "portal", "total": 10}
  ]
}''',
        'response_error_json': '''{
  "error": "Customer usage report not found."
}''',
    }


def _usage_report_customer(base: str) -> dict[str, Any]:
    return {
        'id': 'usage-report-customer',
        'title': 'Download customer usage report',
        'kind': 'endpoint',
        'method': 'GET',
        'path': '/api/usage/report/',
        'description': (
            'Download a customer-specific usage report. Identify the customer with `customer` '
            '(label) or `bucket` (slug). If your API key has a **customer label** set in the '
            'dashboard, omitting scope/customer returns that key customer report automatically.'
        ),
        'parameters': [
            {'name': 'scope', 'type': 'string', 'required': True, 'description': 'Must be `customer` when not using an auto-tagged API key.'},
            {'name': 'customer', 'type': 'string', 'required': False, 'description': 'Customer label, e.g. `Acme Corp`.'},
            {'name': 'bucket', 'type': 'string', 'required': False, 'description': 'Customer bucket slug, e.g. `acme-corp` or `portal`.'},
            {'name': 'period', 'type': 'string', 'required': False, 'description': 'Calendar month as `YYYY-MM`.'},
            {'name': 'export', 'type': 'string', 'required': False, 'description': '`pdf` (default), `csv`, or `json`.'},
        ],
        'responses': [
            {'status': 200, 'description': 'Customer-specific PDF/CSV/JSON report.'},
            {'status': 404, 'description': 'No usage found for that customer in the selected period.'},
        ],
        'curl': f'''curl -o acme-usage.pdf "{base}/api/usage/report/?scope=customer&customer=Acme%20Corp&export=pdf&period=2026-06" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"

curl -o portal-usage.csv "{base}/api/usage/report/?scope=customer&bucket=portal&export=csv" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"''',
        'response_success_json': '''{
  "organization": "Acme Pvt Ltd",
  "period": "2026-06",
  "scope": "customer",
  "customer": {
    "label": "Acme Corp",
    "bucket": "acme-corp",
    "signing_count": 18,
    "gst_count": 4,
    "total": 22,
    "key_names": ["Production"]
  },
  "daily": [
    {"date": "2026-06-09", "signing": 3, "gst": 1, "total": 4}
  ]
}''',
        'response_error_json': '''{
  "error": "Customer usage report not found."
}''',
    }

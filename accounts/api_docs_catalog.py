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
                            'USB tokens) and GST taxpayer lookup services. All tenant APIs use a '
                            'single Bearer API key issued from your dashboard.'
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
                                    'Monthly quotas apply separately for signing and GST calls.',
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
                    _usb_poll_status(base),
                    _usb_download(base),
                ],
            },
            {
                'id': 'gst',
                'title': 'GST Lookup',
                'items': [
                    _gst_gstin_search(base),
                    _gst_preference(base),
                    _gst_return_status(base),
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
                    'Step 1 — Create sign job (POST /api/sign/usb/) with the PDF and target device_id.',
                    'Step 2 — Trigger the local agent (POST http://127.0.0.1:9765/sign) on the Windows PC where the DSC token is plugged in.',
                    'Step 3 — Poll job status (GET /api/sign/usb/{job_id}/) every 2–5 seconds until status is completed.',
                    'Step 4 — Download the signed PDF (GET /api/sign/usb/{job_id}/download/).',
                ],
            },
            {
                'title': 'One-time setup',
                'bullets': [
                    'Create an API key and use Authorization: Bearer dsc_live_… on all cloud API calls.',
                    'On the Windows PC with the Class 3 USB token: Dashboard → USB Agent → download and pair the agent.',
                    'Keep IG E-Sign Agent running in the system tray while signing.',
                    'Note the device_id for each paired machine from the USB Agent page.',
                ],
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
            {'status': 400, 'description': 'Invalid PDF, unknown device, or quota exceeded.'},
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
  "sign_token": "xY7…",
  "expires_at": "2026-06-13T12:30:00+00:00",
  "device_id": 1,
  "document_type": "tax_invoice",
  "hash_before_prefix": "a1b2c3d4",
  "agents_online": 1,
  "agent_sign_url": "http://127.0.0.1:9765/sign",
  "message": "USB sign job prepared."
}''',
        'response_error_json': '''{
  "error": "Agent device not found for this tenant."
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
            'is terminal (completed, failed, or expired).'
        ),
        'parameters': [
            {'name': 'job_id', 'type': 'uuid', 'required': True, 'description': 'Job ID from the create response (path parameter).'},
            {'name': 'include_pdf', 'type': 'integer', 'required': False, 'description': 'Set to `1` to include `signed_pdf_base64` when completed.'},
        ],
        'responses': [
            {'status': 200, 'description': 'Current job status.'},
            {'status': 404, 'description': 'Unknown job ID.'},
        ],
        'curl': f'''curl "{base}/api/sign/usb/JOB_ID/" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"''',
        'response_success_json': '''{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "status": "completed",
  "signing_id": 42,
  "hash_before_prefix": "a1b2c3d4",
  "hash_after_prefix": "e5f6g7h8",
  "document_type": "tax_invoice",
  "error": ""
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
            'Step 4 — Download the signed PDF when status is completed. '
            'Use ?format=json for base64 JSON instead of a file download.'
        ),
        'parameters': [
            {'name': 'job_id', 'type': 'uuid', 'required': True, 'description': 'Completed job ID (path parameter).'},
            {'name': 'format', 'type': 'string', 'required': False, 'description': 'Set to `json` for `signed_pdf_base64` response.'},
        ],
        'responses': [
            {'status': 200, 'description': 'PDF file or JSON with base64 payload.'},
            {'status': 409, 'description': 'Job not yet completed.'},
        ],
        'curl': f'''curl -o signed.pdf "{base}/api/sign/usb/JOB_ID/download/" \\
  -H "Authorization: Bearer dsc_live_YOUR_KEY"''',
        'response_success_json': '''{
  "signed_pdf_base64": "..."
}''',
        'response_error_json': '''{
  "error": "Job is not completed."
}''',
    }


def _usb_local_agent(base: str) -> dict[str, Any]:
    return {
        'id': 'usb-local-agent',
        'title': 'Trigger local agent',
        'kind': 'endpoint',
        'method': 'POST',
        'path': 'http://127.0.0.1:9765/sign',
        'description': (
            'Step 2 — Run on the Windows PC with the Class 3 DSC USB token plugged in. '
            'The IG E-Sign Agent prompts for the token PIN, signs via PKCS#11, and uploads '
            'the result. Uses the one-time sign_token from the create response — not your API key.'
        ),
        'parameters': [
            {'name': 'job_id', 'type': 'uuid', 'required': True, 'description': 'Job ID from create response.'},
            {'name': 'sign_token', 'type': 'string', 'required': True, 'description': 'One-time token from create/poll response.'},
        ],
        'responses': [
            {'status': 200, 'description': 'Agent accepted the signing request.'},
        ],
        'request_json': f'''{{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "sign_token": "xY7…"
}}''',
        'curl': '''curl -X POST "http://127.0.0.1:9765/sign" \\
  -H "Content-Type: application/json" \\
  -d '{
    "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
    "sign_token": "xY7…"
  }' ''',
        'response_success_json': '''{
  "status": "ok",
  "message": "Signing started."
}''',
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
            {'status': 403, 'description': 'Profile incomplete or account not active.'},
            {'status': 429, 'description': 'GST monthly quota exceeded.'},
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

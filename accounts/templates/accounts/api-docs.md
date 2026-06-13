# IG E-Sign API documentation

Integrate PDF signing into your application.

**Base URL:** {{ request.scheme }}://{{ request.get_host }}

**Authentication:** `Authorization: Bearer dsc_live_<your-secret-key>`

---

## Sign a PDF

**POST** `/api/signpdf-pfx`

Provide exactly one of `pfx_base64` or `cert_alias`. No new fields are required — existing integrations keep working.

### Request body (inline PFX)

```json
{
  "pdf_base64": "<base64-encoded PDF>",
  "password": "your-pfx-password",
  "pfx_base64": "<base64-encoded PFX>"
}
```

### Request body (saved cert)

```json
{
  "pdf_base64": "<base64-encoded PDF>",
  "password": "your-pfx-password",
  "cert_alias": "company-dsc"
}
```

### Request body (named signature style)

```json
{
  "pdf_base64": "<base64-encoded PDF>",
  "password": "your-pfx-password",
  "cert_alias": "company-dsc",
  "signature_style": "Invoice"
}
```

`signature_style` is optional. When omitted, your default enabled style is used; if none is enabled, platform defaults apply.

### curl example

```bash
curl -X POST "{{ request.scheme }}://{{ request.get_host }}/api/signpdf-pfx" \
  -H "Authorization: Bearer dsc_live_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_base64": "...",
    "cert_alias": "company-dsc",
    "password": "pfx-password"
  }'
```

### Success response (200)

```json
{
  "message": "PDF signed successfully using PFX.",
  "signed_pdf_base64": "...",
  "signing_id": 42,
  "hash_before_prefix": "a1b2c3d4",
  "hash_after_prefix": "e5f6g7h8"
}
```

`signing_id` correlates with your dashboard activity log. Hash prefixes are the first 8 characters of SHA-256 fingerprints stored server-side for audit.

---

## Sign with USB token (DSC)

Use this flow when the private key stays on a USB DSC token. Your backend prepares the job via API; the **IG E-Sign Agent** on the same Windows PC as the token performs PKCS#11 signing. Poll until complete, then download the signed PDF.

### How it works

1. Your server calls `POST /api/sign/usb/` with the PDF and target `device_id`.
2. On the signing PC, trigger the local agent at `http://127.0.0.1:9765/sign` (user PIN entry on that machine).
3. Your server polls `GET /api/sign/usb/<job_id>/` until `status` is `completed`.
4. Download the signed PDF with `GET /api/sign/usb/<job_id>/download/`.

### One-time setup

1. Create an API key in the portal — use `Authorization: Bearer dsc_live_…` on all USB API calls.
2. On the Windows PC with the USB token: portal → **USB Agent** → download and install the agent.
3. Run `Pair Agent.bat` with a pairing code from the USB Agent page.
4. Start **IG E-Sign Agent** (system tray icon near the clock). Keep it running while signing.
5. Note the `device_id` for that machine (listed on the USB Agent page).

### Step 1 — Create sign job

**POST** `/api/sign/usb/`

```json
{
  "pdf_base64": "<base64-encoded PDF>",
  "device_id": 1,
  "signature_style": "Invoice"
}
```

`device_id` is **required** — the paired agent that will sign this job. `signature_style` is optional (same rules as `/api/signpdf-pfx`). PDF must be a valid file (max 10 MB) and contain the anchor text for the resolved style (default: `Authorised Signatory`).

#### Create response (201)

```json
{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "status": "prepared",
  "sign_token": "xY7…",
  "expires_at": "2026-06-13T12:30:00+00:00",
  "device_id": 1,
  "document_type": "tax_invoice",
  "hash_before_prefix": "a1b2c3d4",
  "agents_online": 1,
  "agent_sign_url": "http://127.0.0.1:9765/sign",
  "message": "USB sign job prepared…"
}
```

`sign_token` is a one-time secret for this job — pass it when triggering the local agent. `agents_online` counts agents that sent a heartbeat in the last ~90 seconds. Jobs expire after 15 minutes if not completed.

#### curl example

```bash
curl -X POST "{{ request.scheme }}://{{ request.get_host }}/api/sign/usb/" \
  -H "Authorization: Bearer dsc_live_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_base64": "'$(base64 -i invoice.pdf | tr -d '\n')'",
    "device_id": 1
  }'
```

### Step 2 — Trigger signing on the Windows PC

Signing happens on the PC with the USB token. From that machine (or a local bridge service), POST to the agent:

**POST** `http://127.0.0.1:9765/sign`

```json
{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "api_base": "{{ request.scheme }}://{{ request.get_host }}",
  "sign_token": "xY7…"
}
```

The agent shows a PIN dialog, signs via PKCS#11, and uploads the result to the cloud. `api_base` must match the portal URL the agent was paired with. For ERP automation, run a small local service on the signing PC that receives `job_id` + `sign_token` from your backend and calls this endpoint.

#### Local trigger curl (run on signing PC)

```bash
curl -X POST "http://127.0.0.1:9765/sign" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
    "api_base": "{{ request.scheme }}://{{ request.get_host }}",
    "sign_token": "xY7…"
  }'
```

### Step 3 — Poll job status

**GET** `/api/sign/usb/<job_id>/`

```json
{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "status": "completed",
  "signing_id": 42,
  "hash_before_prefix": "a1b2c3d4",
  "hash_after_prefix": "e5f6g7h8",
  "document_type": "tax_invoice",
  "error": ""
}
```

Poll every 2–5 seconds until `status` is terminal. While `prepared`, the response includes `sign_token` if you need to re-trigger the agent. Optional: `?include_pdf=1` returns `signed_pdf_base64` when complete.

#### Status values

| Status | Meaning |
|--------|---------|
| `prepared` | Job created; waiting for agent to sign on the Windows PC |
| `completed` | Signed PDF ready — download or use `?include_pdf=1` |
| `failed` | Signing or verification failed — see `error` |
| `expired` | Job timed out before the agent completed signing |

### Step 4 — Download signed PDF

**GET** `/api/sign/usb/<job_id>/download/`

Returns `application/pdf` when `status` is `completed`. Use `?format=json` for `signed_pdf_base64` instead of a file download.

#### curl examples

```bash
# Poll status
curl "{{ request.scheme }}://{{ request.get_host }}/api/sign/usb/JOB_ID/" \
  -H "Authorization: Bearer dsc_live_YOUR_KEY"

# Download PDF file
curl -o signed.pdf "{{ request.scheme }}://{{ request.get_host }}/api/sign/usb/JOB_ID/download/" \
  -H "Authorization: Bearer dsc_live_YOUR_KEY"

# Download as JSON
curl "{{ request.scheme }}://{{ request.get_host }}/api/sign/usb/JOB_ID/download/?format=json" \
  -H "Authorization: Bearer dsc_live_YOUR_KEY"
```

### USB-specific errors

| Status | When | Example |
|--------|------|---------|
| 400 | Unknown or disabled `signature_style` | Signature style not found: 'Invoice' |
| 400 | Missing `device_id`, invalid PDF, anchor not found, or quota exceeded at job create | — |
| 404 | Unknown `job_id` or signed PDF no longer available | Signing job not found. |
| 409 | Download requested before `status` is `completed` | Job is not completed |

---

## Signature placement

The API searches the PDF for an **anchor text** (default: `Authorised Signatory`) and places the signature box just above it. Platform defaults apply unless you create and enable custom styles in the portal.

### Multiple styles

You can maintain multiple named styles under **Signature styles** in the portal (e.g. `Invoice`, `Purchase Order`). Each style can use different anchor text and box offsets.

| API field | Required | Description |
|-----------|----------|-------------|
| `signature_style` | No | Style name to use. Case-insensitive. Must exist and be enabled. |
| *(omitted)* | — | Uses your default enabled style, or platform defaults if none. |

USB signing (`POST /api/sign/usb/`) also accepts optional `signature_style`.

---

## Errors

| Status | When | Example |
|--------|------|---------|
| 401 | Missing or invalid API key | Invalid or revoked API key. |
| 403 | Account not active (pending approval, suspended, etc.) | Your account is awaiting admin approval. |
| 400 | Validation error, bad PFX password, cert not found | Failed to load PFX: invalid password… |
| 400 | Unknown or disabled `signature_style` | Signature style not found: 'Invoice' |
| 400 | Anchor text not found in PDF | No position found for anchor text: 'Authorised Signatory' |
| 429 | Monthly quota exceeded or rate limit | Monthly quota exceeded (100 signs/month). |
| 500 | Unexpected signing failure | Failed to sign PDF: … |

Failed attempts are logged in your dashboard (with hash and IP when the PDF was decoded). Successful signs count toward your monthly quota.

---

## Requirements

- Account status must be **Active**
- Monthly quota: **{{ tenant.monthly_quota }}** signatures ({{ tenant.usage_this_month }} used)
- PDF must contain the anchor text (default `Authorised Signatory`)
- Rate limits apply per API key (burst and hourly limits)
- `pfx_path` is not supported with API key auth — use `pfx_base64` or `cert_alias`

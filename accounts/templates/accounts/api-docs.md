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

Use this flow when the private key stays on a USB DSC token. Your **server** prepares the job and polls for completion; the **IG E-Sign Agent** on the same Windows PC as the token performs PKCS#11 signing when triggered locally.

### How it works

1. Your **server** calls `POST /api/sign/usb/` with the PDF and target `device_id`.
2. On the signing PC, trigger the local agent at `http://127.0.0.1:9765/sign` with `job_id` and `sign_token` (user PIN entry on that machine).
3. Your **server** polls `GET /api/sign/usb/<job_id>/` every 2–5 seconds until `status` is `completed`, `failed`, or `expired`.
4. Your **server** downloads the signed PDF with `GET /api/sign/usb/<job_id>/download/` (or use `?include_pdf=1` on the poll endpoint).

### ERP / browser integrations

| Step | Where to run | Why |
|------|----------------|-----|
| Create job, poll, download | **Your backend server** | Cloud API does not send CORS headers for ERP origins (e.g. Business Central). Use `Authorization: Bearer dsc_live_…` server-side only. |
| Trigger local agent | **Browser or script on signing PC** | Only `http://127.0.0.1:9765` can reach the agent. Add ERP origins to agent `allowed_origins` if calling from a web page. |

Never embed API keys in frontend JavaScript.

### One-time setup

1. Create an API key in the portal — use `Authorization: Bearer dsc_live_…` on all USB API calls.
2. On the Windows PC with the USB token: portal → **USB Agent** → download and install the agent.
3. Pair the agent with a pairing code from the USB Agent page.
4. Start **IG E-Sign Agent** (system tray icon near the clock). Keep it running while signing.
5. Note the `device_id` for that machine (listed on the USB Agent page).

Jobs expire after **15 minutes** if not completed. `agents_online` counts agents that sent a heartbeat in the last **~90 seconds**.

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
}
```

`sign_token` is a one-time secret for this job — pass it when triggering the local agent (not your API key). It is included in poll responses while `status` is `prepared` and cleared after completion.

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

Signing happens on the PC with the USB token. From that machine (browser on an allowed origin, or curl), POST to the agent:

**POST** `http://127.0.0.1:9765/sign`

**Headers**

| Header | Required | Value |
|--------|----------|--------|
| `Content-Type` | Yes | `application/json` |
| `Origin` | Yes | Paired portal URL (e.g. `{{ request.scheme }}://{{ request.get_host }}`) or an ERP origin listed in agent `allowed_origins` |

**Body**

```json
{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "sign_token": "xY7…"
}
```

The agent uses the portal URL from pairing (`api_base` in local config) — you do **not** send `api_base` in the request body. The call is **synchronous**: the response returns only after signing finishes or fails (often 10–30+ seconds). It prompts for the token PIN, signs via PKCS#11, and uploads the result to the cloud.

**CORS:** In the IG E-Sign Agent window, open **Allowed browser origins (ERP / web apps)** and add your ERP URL (e.g. `https://businesscentral.dynamics.com`). Or run `agent.py origins add <url>` on the signing PC. Changes apply immediately. Browsers send an `OPTIONS` preflight first; a disallowed origin gets **403** on preflight.

**Health check (optional):** `GET http://127.0.0.1:9765/health` — see [Local agent health](#local-agent-health) below.

#### Local trigger curl (run on signing PC)

```bash
curl -X POST "http://127.0.0.1:9765/sign" \
  -H "Content-Type: application/json" \
  -H "Origin: {{ request.scheme }}://{{ request.get_host }}" \
  -d '{
    "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
    "sign_token": "xY7…"
  }'
```

#### Agent success response (200)

Returned after the signed PDF is uploaded to the cloud (same shape as `POST /api/agent/jobs/{job_id}/complete/`):

```json
{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "signing_id": 42,
  "hash_after": "e5f6g7h8a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef01234567"
}
```

`hash_after` is the full SHA-256 hex digest of the signed PDF (not the 8-character prefix used on tenant poll/download APIs).

#### Local agent errors (POST /sign)

All error responses are JSON: `{"error": "<message>"}` unless noted.

| HTTP | When | Example `error` |
|------|------|-----------------|
| **400** | Missing `job_id` / `sign_token`, or agent not paired | `Agent is not paired or job_id/sign_token missing.` |
| **403** | No `Origin` header | `Origin header is required for local signing.` |
| **403** | `Origin` not in allowlist | `Origin is not allowed for this agent.` |
| **404** | Wrong URL path | HTML error page (not JSON) |
| **500** | Job not found / bad token / expired | `{"error": "Signing job not found."}` (may be embedded in `error` string) |
| **500** | Wrong device for job | `Signing job is assigned to another agent.` |
| **500** | USB / PIN / PKCS#11 failure | `USB token signing failed: …` |
| **500** | Signed PDF rejected by cloud | `Signed PDF is identical to the original — no signature was applied.` |
| **500** | Device token revoked | Agent clears pairing; re-pair from the portal |

After a **200** response, your server should poll `GET /api/sign/usb/<job_id>/` — status should already be `completed`.

#### Local agent health

**GET** `http://127.0.0.1:9765/health`

`Origin` is optional for curl; include it for browser checks from an ERP page.

```json
{
  "ok": true,
  "version": "0.1.0",
  "token_present": true,
  "portal_paired": true,
  "portal_connected": true,
  "token_count": 1,
  "selected_token_display": "eMudhra — DS Example"
}
```

| Field | Meaning |
|-------|---------|
| `token_present` | USB DSC token detected |
| `portal_paired` | `device_token` exists in local config |
| `portal_connected` | Recent successful heartbeat to the cloud |
| `token_count` / `selected_token_display` | PKCS#11 token slot summary |

---

### Step 3 — Poll job status

**GET** `/api/sign/usb/<job_id>/`

Call from your **server** (not from an ERP browser page).

#### While waiting (`prepared`)

```json
{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "status": "prepared",
  "expires_at": "2026-06-13T12:30:00+00:00",
  "signing_id": null,
  "hash_before_prefix": "a1b2c3d4",
  "hash_after_prefix": "",
  "error": "",
  "device_id": 1,
  "document_type": "tax_invoice",
  "sign_token": "xY7…"
}
```

There is no separate `signing` status — while the agent is working, status remains `prepared`.

#### When complete

```json
{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "status": "completed",
  "expires_at": "2026-06-13T12:30:00+00:00",
  "signing_id": 42,
  "hash_before_prefix": "a1b2c3d4",
  "hash_after_prefix": "e5f6g7h8",
  "error": "",
  "device_id": 1,
  "document_type": "tax_invoice"
}
```

Poll every 2–5 seconds until `status` is terminal. Optional: `?include_pdf=1` adds `signed_pdf_base64` when `status` is `completed`.

#### Status values

| Status | Meaning |
|--------|---------|
| `prepared` | Job created; waiting for agent to sign on the Windows PC |
| `completed` | Signed PDF ready — download or use `?include_pdf=1` |
| `failed` | Signing or verification failed — see `error` |
| `expired` | Job timed out (15 minutes) before the agent completed signing |

### Step 4 — Download signed PDF

**GET** `/api/sign/usb/<job_id>/download/`

Call from your **server** when poll `status` is `completed`.

#### Binary file (default)

- **Content-Type:** `application/pdf`
- **Content-Disposition:** `attachment; filename="signed-<job_id>.pdf"`
- **Body:** raw PDF bytes

```bash
curl -o signed.pdf "{{ request.scheme }}://{{ request.get_host }}/api/sign/usb/JOB_ID/download/" \
  -H "Authorization: Bearer dsc_live_YOUR_KEY"
```

#### JSON (`?format=json`)

```json
{
  "job_id": "a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7",
  "signed_pdf_base64": "JVBERi0xLjQKJ...",
  "signing_id": 42,
  "hash_after_prefix": "e5f6g7h8"
}
```

```bash
curl "{{ request.scheme }}://{{ request.get_host }}/api/sign/usb/JOB_ID/download/?format=json" \
  -H "Authorization: Bearer dsc_live_YOUR_KEY"
```

#### Poll shortcut

```bash
curl "{{ request.scheme }}://{{ request.get_host }}/api/sign/usb/JOB_ID/?include_pdf=1" \
  -H "Authorization: Bearer dsc_live_YOUR_KEY"
```

Returns the usual poll fields plus `signed_pdf_base64` when `status` is `completed`.

### USB-specific errors

| Status | When | Example |
|--------|------|---------|
| 400 | Unknown/disabled `signature_style`, invalid PDF, anchor not found, quota exceeded | `{"error": "No position found for anchor text: 'Authorised Signatory'"}` |
| 400 | Invalid `device_id` at create | `{"device_id": ["Agent device not found for this tenant."]}` |
| 403 | Account not active at create | `{"error": "Your account is awaiting admin approval."}` |
| 404 | Unknown `job_id` | `{"error": "Signing job not found."}` |
| 404 | Completed job but PDF missing | `{"error": "Signed PDF is not available."}` |
| 409 | Download before `completed` | `{"error": "Job is not completed (status=prepared)."}` |

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

## Team members (portal)

IG E-Sign supports optional **team members** for portal and USB signing under the same organization.

| Topic | Detail |
|--------|--------|
| Who can invite | Organization **owners** only (`/dashboard/team/`) |
| Member access | Portal sign, USB sign, signature styles (read-only), API docs |
| Member restrictions | No API keys, saved certs, GST profile, usage exports, or agent pairing |
| API integrations | Unchanged — use your existing `dsc_live_…` key; API calls are **organization-scoped**, not per-user |
| Quota | Shared across the organization (owner + members) |
| GST API | Still authenticated with the owner-managed API key; members do not manage GST settings |

Team invites require `TEAMS_ENABLED` on the server. Until enabled, every account remains a single owner with full access.

---

## Requirements

- Account status must be **Active**
- Quota: **{{ quota.limit }}** signatures ({{ quota.used }} used){% if quota.is_term_based %} — term plan, expires {{ quota.resets_or_expires_at|date:"M j, Y" }}{% else %} — resets monthly{% endif %}
- PDF must contain the anchor text (default `Authorised Signatory`)
- Rate limits apply per API key (burst and hourly limits)
- `pfx_path` is not supported with API key auth — use `pfx_base64` or `cert_alias`

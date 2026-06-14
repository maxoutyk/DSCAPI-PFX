# Security Audit — IG E-Sign

**Initial audit:** 2026-06-12  
**Comprehensive review:** 2026-06-09  
**Scope:** Django SaaS portal, REST signing API, public visual sign, USB desktop agent (`feature/usb-dsc-agent`)  
**Branch:** `feature/usb-dsc-agent`

---

## Production configuration (confirmed)

Production at `sign.incitegravity.com` is configured as follows:

| Setting | Production status |
|---------|-------------------|
| `SECRET_KEY` | Set via `.env` (not using dev fallback) |
| `ENCRYPTION_KEY` | Set via `.env` (independent Fernet key) |
| `DEBUG` | `false` |
| Secure cookies / HSTS | Enabled when `DEBUG=false` (see `DSCApi/settings.py`) |
| `ALLOW_BASIC_AUTH` | Default `false` unless explicitly overridden |

With this configuration, several findings below are **dev/misconfiguration risks only** and do not apply to the current production deployment. They remain relevant for local development, staging, and any future environment that omits these settings.

---

## Summary

### Remediated on this branch

| Severity | Count | Notes |
|----------|-------|-------|
| Critical | 2 | C2, C3 — secret/encryption key handling |
| High | 5 | H1 (pairing), H3 (API PDF limits), H4 (basic auth default), H5 (DB cache), partial H2 (`sign_token`) |
| Medium | 8 | M1–M4, M6–M8, M10 |

### Open findings (action required or tracked)

| Severity | Count | Status |
|----------|-------|--------|
| Critical | 0 | C1 fixed — incremental PDF prefix binding |
| High | 1 | H6 documented (PFX passwords in JSON) |
| Medium | 2 | M9 deferred (agent token OS store), M15 accepted (public sign) |
| Low | 2 | L2/L5 N/A in production; L6 dead config |

**Fixed 2026-06-09:** C1, H2, H3b, H5b, H7, H8, H9, M5, M11, M12, M13, L4, L7 — see changelog.

---

## Architecture & attack surface

```
Public          →  /sign/free/, /api/agent/pair/
Portal (session)→  /dashboard/*, certs, sign, USB agent
API (API key)   →  /api/signpdf-pfx, /api/sign/usb/*
Agent (token)   →  /api/agent/heartbeat/, /api/agent/jobs/*
Local agent     →  127.0.0.1:9765 (/health, /sign) — desktop bridge
```

Sensitive data at rest: Fernet-encrypted PFX (`StoredCertificate`), USB job PDFs, portal/public sign artifacts. PFX passwords are **not** stored — required per sign request.

---

## Critical

### C1 — USB signed PDF is not bound to the prepared document *(FIXED)*

**Files:** `usb_agent/verification.py`, `usb_agent/services.py`

**Fix:** Reject submissions where `signed_pdf` does not start with the prepared `original_pdf` bytes (endesive incremental signing appends to the original). Failed jobs persist as `failed` outside the success transaction.

---

### C2 — Hardcoded `SECRET_KEY` fallback *(REMEDIATED — mitigated in production)*

**Risk:** Predictable sessions/CSRF if `SECRET_KEY` unset.  
**Fix:** `ImproperlyConfigured` when missing and `DEBUG=false` (non-frozen builds). Dev uses explicit insecure fallback only when `DEBUG=true`.  
**Production:** `.env` provides `SECRET_KEY` — not affected.

---

### C3 — `ENCRYPTION_KEY` derived from `SECRET_KEY` *(REMEDIATED — mitigated in production)*

**Risk:** Cross-environment ciphertext decryption if keys are coupled.  
**Fix:** Independent `ENCRYPTION_KEY` required when `DEBUG=false`; documented in `.env.example`.  
**Production:** `.env` provides `ENCRYPTION_KEY` — not affected.

**Dev note:** When `DEBUG=true`, a known default Fernet key is used (`DSCApi/settings.py`). This is acceptable for local dev only; never copy a dev database encrypted with the default key into a shared environment.

---

## High

### H1 — Weak pairing codes, no rate limit *(REMEDIATED)*

**Fix:** `secrets.token_urlsafe(16)` pairing codes; `AgentPairThrottle` on `POST /api/agent/pair/`.

---

### H2 — Local agent CORS and `/sign` endpoint *(PARTIALLY REMEDIATED — gaps remain)*

**Remediated:** Per-job `sign_token` required for agent job fetch/complete; CORS allowlist tied to paired `api_base` when `Origin` is present.

**Open — H2a:** Local agent accepts `api_base` from POST body (`desktop-agent/agent.py`), not pinned to paired config. A local attacker can redirect the agent to a malicious API.

**Open — H2b:** CORS is skipped when `Origin` header is absent. Local scripts/malware can call `/sign` without browser CORS checks if they possess `job_id` + `sign_token`.

**Recommended fix:** Pin `api_base` to paired config only; require local shared secret or always reject `/sign` without allowed Origin.

---

### H3 — No API PDF size limits *(REMEDIATED for PDF)*

**Fix:** `signPdf/validation.py` — `decode_pdf_base64()` enforces `API_SIGN_MAX_UPLOAD_BYTES` and `%PDF` magic bytes on `/api/signpdf-pfx` and `/api/sign/usb/`.

**Open — H3b:** `pfx_base64` on `/api/signpdf-pfx` is decoded without length cap (`signPdf/views.py`). Memory exhaustion risk.

**Recommended fix:** Apply `_max_base64_length()` pattern to PFX base64 before decode.

---

### H4 — `ALLOW_BASIC_AUTH` in dev/LAN *(REMEDIATED — mitigated in production)*

**Fix:** Default `ALLOW_BASIC_AUTH=false`. When enabled, Basic auth bypasses tenant audit/quota and allows `pfx_path` reads within `PFX_CERTS_DIR`.  
**Production:** Default `false` — not affected unless explicitly enabled.

---

### H5 — `LocMemCache` rate limits with multiple workers *(REMEDIATED — mitigated in production)*

**Fix:** Database cache backend when `DEBUG=false` and `CACHE_BACKEND` unset; `createcachetable` in Docker entrypoint.  
**Production:** `DEBUG=false` uses DB cache by default. Set `CACHE_BACKEND=database` explicitly in `.env` for clarity (see `.env.example`).

**Open — H5b:** `SafeSimpleRateThrottle` and `accounts/safe_cache.py` **fail open** if cache errors — throttling disabled when cache is down. Monitor cache health in production.

---

### H6 — PFX passwords in API JSON bodies *(DOCUMENTED — ongoing risk)*

**Risk:** Reverse proxies, APM, or application logs may capture `password` from request bodies.  
**Mitigation:** Never log request bodies on signing endpoints; prefer `cert_alias` with stored encrypted PFX. Documented in API docs.

---

### H7 — Portal PDF upload lacks content validation *(OPEN)*

**Files:** `accounts/forms.py` (`PortalSignForm`), `accounts/views.py` (`sign_view`, `sign_preview_view`)

Portal PFX signing checks file extension and size only — no `validate_pdf_bytes()`. USB portal form and public sign paths **do** validate.

**Risk:** Malicious/crafted PDFs against PyMuPDF/endesive (parser bugs, CPU/memory exhaustion).

**Recommended fix:** Call `validate_pdf_bytes()` in `PortalSignForm.clean_pdf_file` and the preview endpoint.

---

### H8 — PFX file upload has no size limit *(OPEN)*

**File:** `accounts/forms.py` (`CertificateUploadForm`)

Entire PFX read into memory with no max size before PKCS12 parse.

**Recommended fix:** Enforce max upload size (e.g. 5 MB) before `load_pfx_credentials()`.

---

### H9 — Unbounded `signed_pdf_base64` on agent job completion *(OPEN)*

**File:** `usb_agent/api_views.py`

`base64.b64decode(signed_b64)` with no length cap. Authenticated agent token required, but stolen token could exhaust memory.

**Recommended fix:** Cap base64 length and decoded bytes (same limit as `API_SIGN_MAX_UPLOAD_BYTES`).

---

## Medium

### M1 — USB jobs prepared without quota check *(REMEDIATED)*

**Fix:** `ensure_tenant_has_quota` in `prepare_usb_sign_job`.

---

### M2 — `X-Forwarded-For` trusted without proxy config *(REMEDIATED)*

**Fix:** `TRUSTED_PROXY_COUNT` — only parse forwarded headers when set. Production should set `TRUSTED_PROXY_COUNT=1` behind Caddy/nginx.

---

### M3 — Full signed PDF in session *(REMEDIATED)*

**Fix:** `PortalSignArtifact` / `PublicSignArtifact` models; session stores artifact UUID only.

---

### M4 — `SECURE_COOKIES` default in production *(REMEDIATED — active in production)*

**Fix:** Defaults to `true` when `DEBUG=false`. Production with `DEBUG=false` has secure session/CSRF cookies and HSTS.

---

### M5 — No Content-Security-Policy *(OPEN — documented)*

No CSP in Django or `deploy/Caddyfile`. XSS in any template would have full script capability.

**Recommended fix:** Add CSP, `X-Frame-Options`, and related headers at Caddy/nginx (defense in depth). See deploy notes.

---

### M6 — PDF validation is shallow *(PARTIALLY REMEDIATED)*

**Fix:** `%PDF` magic-byte check on API and some portal paths.  
**Open:** No page-count bomb limits, compression bomb checks, or structural PDF validation. Extension-only checks on some upload forms.

---

### M7 — Short pairing codes in UI *(REMEDIATED)*

Resolved by H1 (long URL-safe codes).

---

### M8 — `sign_usb_view` null tenant crash *(REMEDIATED)*

**Fix:** Tenant guard before status check in USB portal views.

---

### M9 — Agent token plaintext on disk *(DEFERRED)*

**File:** `desktop-agent/agent.py` — `device_token` in `~/.ig-esign-agent/config.json`.  
**Status:** Deferred — migrate to OS credential store in a future agent release.

---

### M10 — First agent claims unassigned jobs *(REMEDIATED)*

**Fix:** API-created jobs require `device_id`; portal jobs bind at prepare when exactly one device is online.

---

### M11 — No RBAC enforcement *(OPEN)*

**Files:** `accounts/models.py` (`MembershipRole`), all portal views

`owner` / `member` roles exist but are never enforced. Any logged-in primary member can create/revoke API keys, upload certs, pair agents, and sign.

**Recommended fix:** Enforce role checks on destructive operations, or document that all members are full administrators.

---

### M12 — Null tenant causes 500 on portal views *(OPEN)*

**File:** `accounts/views.py`

`get_primary_tenant()` can return `None`; views such as `dashboard_view` dereference `tenant` without guard.

**Recommended fix:** Redirect users without membership to onboarding or return 403.

---

### M13 — Agent heartbeat/job endpoints unthrottled *(OPEN)*

**File:** `usb_agent/api_views.py`

Stolen `dsc_agent_*` token could spam heartbeat or poll jobs. Lower severity due to token entropy.

---

### M14 — `sign_token` exposed in API poll responses *(BY DESIGN)*

**File:** `usb_agent/services.py` — `build_job_status_payload` includes `sign_token` while status is `prepared`.

Required for ERP/automation flows. Increases blast radius if API key leaks (key holder can create jobs and obtain tokens). Document for integrators.

---

### M15 — Public `/sign/free/` is unauthenticated *(ACCEPTED RISK)*

**File:** `accounts/public_sign_views.py`

IP rate-limited (default 10 requests / 15 min). Visual stamp only (not DSC). Consider WAF/CDN protection for abuse.

---

## Low (documented)

| ID | Finding | Status |
|----|---------|--------|
| L1 | SHA-256 API/agent token hashes (no salt) | Acceptable for high-entropy tokens |
| L2 | `DEBUG=true` serves `/media/` publicly | Not applicable — production `DEBUG=false` |
| L3 | Admin bootstrap password in `.env` | Rotate after first deploy |
| L4 | Security headers not in `deploy/Caddyfile` | Add at reverse proxy |
| L5 | Frozen builds use `ALLOWED_HOSTS=['*']` | Desktop/on-prem builds only |
| L6 | `USB_AGENT_ALLOWED_ORIGINS` defined but unused in Django | Dead config; agent uses `api_base` origin |
| L7 | `Content-Disposition` filename from user upload name | Theoretical header injection; sanitize if hardening |
| L8 | Plaintext device token in local agent config | See M9 |

---

## Strengths (controls in place)

- Independent `SECRET_KEY` and `ENCRYPTION_KEY` in production `.env`
- API key and agent token auth via prefix + SHA-256 hash lookup
- Fernet encryption for stored PFX, USB job PDFs, sign artifacts
- Per-job `sign_token` for USB agent fetch/complete
- `device_id` required on API USB job creation
- USB completion runs endesive CMS verification (partial — see C1)
- Pairing code entropy + throttle on `/api/agent/pair/`
- PFX path traversal guard for on-prem `pfx_path` mode
- `TRUSTED_PROXY_COUNT` for client IP in audit logs
- No raw SQL; templates use autoescape; no `csrf_exempt`
- Production session cookies: `HttpOnly`, `Secure`, HSTS when `DEBUG=false`

---

## Production deployment checklist

Current production meets the critical items below. Use this checklist for new environments or redeploys.

```bash
# Required (confirmed in production .env)
SECRET_KEY=<random-50+chars>          # ✓ set
ENCRYPTION_KEY=<Fernet.generate_key()> # ✓ set
DEBUG=false                            # ✓ set
ALLOWED_HOSTS=sign.incitegravity.com
CSRF_TRUSTED_ORIGINS=https://sign.incitegravity.com
SECURE_COOKIES=true
ALLOW_BASIC_AUTH=false
TRUSTED_PROXY_COUNT=1                  # behind Caddy/nginx
CACHE_BACKEND=database                 # shared rate limits across workers

# After deploy
python manage.py createcachetable
python manage.py migrate
```

### Reverse proxy (recommended additions)

`deploy/Caddyfile` currently proxies only. Consider adding:

- `Content-Security-Policy`
- `X-Frame-Options: DENY` (Django sets frame options; belt-and-suspenders at proxy)
- `Permissions-Policy`

### Operational practices

- Never log request bodies on `/api/signpdf-pfx` or `/api/sign/usb/` (PFX passwords).
- Rotate API keys and revoke compromised keys promptly.
- Rotate `ADMIN_PASSWORD` after first deploy.
- Monitor cache/DB health — rate limits fail open on cache errors.

---

## Priority remediation roadmap

| Priority | ID | Action | Production impact |
|----------|-----|--------|-------------------|
| **P0** | C1 | Bind USB signed PDF to prepared document | **Affects production** |
| **P1** | H7 | `validate_pdf_bytes` on portal PDF sign/preview | Affects production |
| **P1** | H3b, H9 | Cap PFX and signed-PDF base64 sizes | Affects production |
| **P1** | H8 | PFX upload size limit | Affects production |
| **P1** | H2a, H2b | Pin agent `api_base`; harden local `/sign` | Desktop agent update |
| **P2** | M11, M12 | RBAC or document; null-tenant guards | Affects production |
| **P2** | M5, L4 | CSP and security headers in Caddy | Infrastructure |
| **P2** | H5b | Alert on cache/throttle fail-open | Operations |
| **P3** | M13 | Agent endpoint throttling | Low urgency |

---

## Verification tests

```bash
python manage.py test usb_agent signPdf accounts
```

---

## Change log

| Date | Change |
|------|--------|
| 2026-06-12 | Initial audit; remediated C2, C3, H1, H3–H5, M1–M4, M6–M8, M10 |
| 2026-06-09 | Comprehensive review; confirmed production `.env` + `DEBUG=false` |
| 2026-06-09 | Security remediation: C1, H2–H9 (except H6), M5/M11–M13, L4/L7; tests added |

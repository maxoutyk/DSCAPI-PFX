# Security Audit — IG E-Sign

**Date:** 2026-06-12  
**Scope:** Django SaaS + USB desktop agent (`feature/usb-dsc-agent`)  
**Status:** Remediation complete on this branch (see checklist below)

## Summary

| Severity | Count | Fixed in branch |
|----------|-------|-----------------|
| Critical | 3 | 3 |
| High | 6 | 5 (H6 documented) |
| Medium | 10 | 9 (M5 documented, M9 deferred) |
| Low | 6 | 3 documented |

---

## Critical

### C1 — USB completion did not verify signatures
**Risk:** Rogue agent uploads unsigned PDF; audit shows success.  
**Fix:** `usb_agent/verification.py` validates PDF signatures via endesive before `complete_usb_sign_job`.

### C2 — Hardcoded `SECRET_KEY` fallback
**Risk:** Predictable sessions/CSRF if env unset.  
**Fix:** `ImproperlyConfigured` when `SECRET_KEY` missing (non-frozen builds).

### C3 — `ENCRYPTION_KEY` derived from `SECRET_KEY`
**Risk:** Cross-environment ciphertext decryption.  
**Fix:** Independent `ENCRYPTION_KEY` required; dev-only auto-generate documented in `.env.example`.

---

## High

### H1 — 6-digit pairing codes, no rate limit
**Risk:** Brute-force agent pairing within TTL.  
**Fix:** 128-bit URL-safe pairing codes; `AgentPairThrottle` on `POST /api/agent/pair/`.

### H2 — Localhost agent CORS + unauthenticated `/sign`
**Risk:** Malicious websites trigger signing via `127.0.0.1:9765`.  
**Fix:** Per-job `sign_token` required; agent job fetch validates token; CORS allowlist.

### H3 — No API PDF size limits
**Risk:** Memory/DB DoS via huge `pdf_base64`.  
**Fix:** `signPdf/validation.py` enforces `API_SIGN_MAX_UPLOAD_BYTES` on all signing APIs.

### H4 — `ALLOW_BASIC_AUTH` when `DEBUG=true`
**Risk:** Unaudited on-prem signing in dev/LAN.  
**Fix:** Default `ALLOW_BASIC_AUTH=false`; explicit opt-in only.

### H5 — `LocMemCache` rate limits with multiple workers
**Risk:** Effective limits multiplied per Gunicorn worker.  
**Fix:** Database cache backend in production; `createcachetable` in Docker entrypoint.

### H6 — PFX passwords in API JSON bodies
**Risk:** Proxy/APM logs may capture passwords.  
**Mitigation:** Documented in this file and API docs — never log request bodies; use stored `cert_alias` where possible.

---

## Medium

### M1 — USB jobs prepared without quota check
**Fix:** `ensure_tenant_has_quota` in `prepare_usb_sign_job`.

### M2 — `X-Forwarded-For` trusted without proxy config
**Fix:** `TRUSTED_PROXY_COUNT` — only parse forwarded headers when set.

### M3 — Full signed PDF in session
**Fix:** `PortalSignArtifact` model; session stores artifact UUID only.

### M4 — `SECURE_COOKIES` default false in production block
**Fix:** Default `SECURE_COOKIES=true` when `DEBUG=false`.

### M5 — No Content-Security-Policy
**Status:** Documented; add at Caddy/reverse-proxy (see deploy notes).

### M6 — PDF extension-only validation
**Fix:** Magic-byte `%PDF` check in `signPdf/validation.py`.

### M7 — Short pairing codes in UI
**Fix:** Resolved by H1 (long codes).

### M8 — `sign_usb_view` null tenant crash
**Fix:** Tenant guard before status check.

### M9 — Agent token plaintext on disk
**Status:** Deferred — use OS credential store in future agent release.

### M10 — First agent claims unassigned jobs
**Fix:** API-created jobs require `device_id`; portal jobs bind at prepare when one device online.

---

## Low (documented)

- **L1:** SHA-256 token hashes — acceptable for high-entropy tokens.
- **L3:** Admin bootstrap password in `.env` — rotate after first deploy.
- **L4:** Add security headers in Caddy for defense in depth.

---

## Deployment checklist

```bash
# Required production env
SECRET_KEY=<random-50+chars>
ENCRYPTION_KEY=<Fernet.generate_key()>
DEBUG=false
ALLOWED_HOSTS=sign.example.com
CSRF_TRUSTED_ORIGINS=https://sign.example.com
SECURE_COOKIES=true
ALLOW_BASIC_AUTH=false
TRUSTED_PROXY_COUNT=1   # if behind Caddy/nginx

# After deploy
python manage.py createcachetable
python manage.py migrate
```

## Verification tests

```bash
python manage.py test usb_agent signPdf accounts
```

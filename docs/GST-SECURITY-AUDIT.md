# GST Lookup Module — Security Audit

**Date:** 2026-06-14  
**Scope:** `gst/` app, company profile gating, MyGSTCafe partner client, portal console, REST API  
**Status:** Findings documented; remediations applied in this changeset.

---

## Architecture

```
Tenant API key  →  /api/gst/*           →  lookup_handlers  →  GST partner (server-only URL)
Portal session  →  /dashboard/gst/try/  →  lookup_handlers  →  GST partner (server-only URL)
```

**Trust boundaries**

| Asset | Exposure |
|-------|----------|
| Partner base URL (`GST_PARTNER_BASE_URL`) | Server env/settings only — **never** in JS, templates, or tenant API responses |
| Partner credentials (`GST_MYGSTCAFE_*`) | Server env only |
| Tenant GSTIN | Defaults to `CompanyProfile.gstin` when omitted; any valid GSTIN allowed within quota |
| Lookup results | Returned to authenticated tenant only |

---

## Findings Summary

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| GST-H1 | **High** | Portal try used GET → CSRF quota burning | **Fixed** — POST + CSRF |
| GST-H2 | **High** | Portal bypassed API rate limits | **Fixed** — per-tenant portal throttling |
| GST-M1 | **Medium** | Quota checked after partner call | **Fixed** — `ensure_gst_quota_remaining()` before outbound call |
| GST-M2 | **Medium** | Non-owner members could run portal lookups | **Fixed** — owner-only on portal try |
| GST-M3 | **Medium** | GSTIN format not validated on lookup path | **Fixed** — `gst/validation.py` + `resolve_tenant_gstin()` |
| GST-M4 | **Medium** | Partner `errorMessage` forwarded to clients | **Fixed** — generic public error messages |
| GST-M5 | **Medium** | Non-JSON partner bodies returned as `raw` text | **Fixed** — reject/sanitize; no raw forward |
| GST-M6 | **Medium** | Partner URL in client code risk | **Fixed** — URL only in `GST_PARTNER_BASE_URL` server setting |
| GST-L1 | **Low** | GST API throttles not fail-closed | **Fixed** — `FailClosedSimpleRateThrottle` |
| GST-L2 | **Low** | `is_complete` did not validate GSTIN format | **Mitigated** — lookup path validates format |
| GST-L3 | **Low** | Limited security test coverage | **Partially fixed** — new portal security tests |

---

## Finding Details

### GST-H1 — GET portal try enabled CSRF quota burning

**Risk:** Malicious page could trigger `GET /dashboard/gst/try/?endpoint=...` while victim is logged in, consuming monthly quota and partner credits.

**Fix:** `gst/portal_try.py` now requires `POST`. `gst-console.js` sends `FormData` with `X-CSRFToken`. CSRF token rendered in dashboard template.

---

### GST-H2 — Portal bypassed API throttles

**Risk:** API capped at 20/min and 120/hour per tenant; portal had no limits.

**Fix:** `gst/portal_ratelimit.py` enforces the same scopes (`gst_lookup_burst`, `gst_lookup`) per tenant. Returns 429 when exceeded. Fails closed if cache unavailable.

---

### GST-M1 — Quota after partner call

**Risk:** Partner billed even when tenant over monthly quota; race at quota boundary.

**Fix:** `ensure_gst_quota_remaining()` uses `select_for_update()` before outbound HTTP in all three handlers.

---

### GST-M2 — Member role portal access

**Risk:** Any primary-tenant member could spend GST quota via portal.

**Fix:** Portal try returns 403 unless `user_is_tenant_owner()`.

---

### GST-M3 — GSTIN validation gap

**Risk:** Invalid GSTIN from admin/ORM could reach partner.

**Fix:** Shared `gst/validation.py`; `resolve_tenant_gstin()` validates profile and request GSTIN. `CompanyProfileForm` imports same regex.

---

### GST-M4 / GST-M5 — Partner error leakage

**Risk:** Partner error text or HTML error pages exposed in API/portal JSON.

**Fix:** `gst/client.py` maps HTTP status to safe messages; logs details server-side only; non-JSON error responses never forwarded as `raw`.

---

### GST-M6 — Partner URL must not reach clients

**Policy:** End users must not see or call the MyGSTCafe host directly (tracing / coupling).

**Controls:**
- `GST_PARTNER_BASE_URL` in `DSCApi/settings.py` and `.env` only
- `gst/client.py` reads URL from settings — no constant in frontend
- Grep verification: no `mygstcafe` in templates, JS, or public API docs
- All tenant traffic goes through IG E-Sign `/api/gst/*` or `/dashboard/gst/try/`

---

### GST-L1 — Fail-open throttles

**Fix:** `gst/throttling.py` uses `FailClosedSimpleRateThrottle` (aligned with signing API).

---

## Positive Controls (unchanged)

- Quota + rate limits on arbitrary GSTIN lookups; `GstApiLog` records searched GSTIN
- API key SHA-256 hashing + `IsAPIKeyAuthenticated`
- Active tenant + complete company profile gates
- Fixed partner paths (SSRF-resistant)
- Atomic quota increment on success only
- FY regex + return type whitelist
- Portal endpoint allowlist
- XSS escaping in portal JS summary
- `GstApiLog` audit trail

---

## Verification Checklist

- [ ] `python manage.py test gst.tests gst.test_portal`
- [ ] Confirm no `mygstcafe` in `accounts/static`, `gst/static`, `accounts/templates`, `gst/templates`
- [ ] Portal lookup works via POST from dashboard
- [ ] GET `/dashboard/gst/try/` returns 405
- [ ] Non-owner member receives 403 on portal try

---

## Files Changed (remediation)

| File | Change |
|------|--------|
| `gst/portal_try.py` | POST, CSRF, owner check, rate limit |
| `gst/portal_ratelimit.py` | New — portal throttling |
| `gst/validation.py` | New — shared GSTIN validation |
| `gst/services.py` | Quota pre-check, GSTIN validation |
| `gst/client.py` | Settings URL, sanitized errors |
| `gst/throttling.py` | Fail-closed throttles |
| `gst/lookup_handlers.py` | Quota before partner, GSTIN errors |
| `gst/static/gst/js/gst-console.js` | POST + CSRF |
| `gst/templates/gst/dashboard.html` | CSRF token |
| `DSCApi/settings.py` | `GST_PARTNER_BASE_URL` |
| `.env.example` | Document partner URL as server-only |
| `accounts/forms.py` | Shared GSTIN validation |

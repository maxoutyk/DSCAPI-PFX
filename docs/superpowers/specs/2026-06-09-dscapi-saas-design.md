# DSCAPI SaaS Design Spec

**Date:** 2026-06-09  
**Status:** Approved

## Goal

Transform DSCAPI-PFX from a single-tenant Windows appliance into a multi-tenant SaaS PDF signing service with user registration, email verification, admin approval, API keys, saved certificates, and usage quotas — deployable on Linux.

## Decisions

| Topic | Choice |
|-------|--------|
| PFX delivery | Per-request `pfx_base64` + saved certs per tenant |
| Customer UI | Django template web portal |
| Access model | Free tier (100 signs/month default) + manual admin approval |
| Email | Required verification before approval queue |
| Account model | Single user per tenant now; `TenantMembership` for future orgs |
| Architecture | Extend Django monolith with `accounts` app |

## Components

### Data model

- **Tenant** — org account with status, quota, usage counter
- **TenantMembership** — links User ↔ Tenant with role (owner/member)
- **APIKey** — hashed keys with visible prefix, revoke support
- **StoredCertificate** — Fernet-encrypted PFX per tenant
- **UsageLog** — audit trail and quota enforcement
- **EmailVerificationToken** — one-time email confirmation links

### Auth

| Surface | Method |
|---------|--------|
| Portal | Django session (email + password) |
| Signing API | `Authorization: Bearer dsc_live_...` |
| On-prem fallback | HTTP Basic Auth (Windows .exe) |

### Account lifecycle

`register` → `pending_email` → verify email → `pending_approval` → admin approve → `active`

### Signing API

`POST /api/signpdf-pfx` accepts `pdf_base64`, `password`, and exactly one of:
- `pfx_base64` (inline)
- `cert_alias` (saved tenant cert)

Legacy `pfx_path` remains for Basic Auth on-prem mode only.

### Security

- API keys: SHA-256 hash at rest, shown once on creation
- Saved PFX: Fernet encryption via `ENCRYPTION_KEY`
- Tenant isolation on all keys, certs, and usage
- Secrets from environment variables in production

### Out of scope (v1)

Billing/Stripe, team invites, webhooks, per-tenant signature styling.

## Deployment

- **Dev:** SQLite, console email backend
- **Production:** PostgreSQL, SMTP, Gunicorn + Nginx on Linux (Phase 5)

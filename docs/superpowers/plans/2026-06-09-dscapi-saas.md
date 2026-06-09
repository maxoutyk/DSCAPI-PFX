# DSCAPI SaaS Implementation Plan

> **Goal:** Multi-tenant PDF signing SaaS with registration, API keys, saved certs, quotas, and web portal.

**Architecture:** Extend Django monolith with `accounts` app; API key auth on signing endpoint; Django templates for portal.

**Tech Stack:** Django 5, DRF, Fernet encryption, SQLite (dev) / PostgreSQL (prod)

---

## Phase 1 — Foundation ✅
- `accounts` models: Tenant, APIKey, StoredCertificate, UsageLog
- API key authentication + tenant services
- Encrypted certificate storage

## Phase 2 — Portal ✅
- Registration, email verification, login, dashboard
- API key and certificate management pages
- API docs page

## Phase 3 — Signing integration ✅
- Updated `/api/signpdf-pfx` for API keys + `cert_alias`
- Quota enforcement and usage logging
- Basic Auth fallback for on-prem Windows .exe

## Phase 4 — Admin ✅
- Django admin approve/suspend actions

## Phase 5 — Linux deploy ✅
- `Dockerfile` + `docker-compose.yml` (web, PostgreSQL, nginx)
- `deploy/nginx.conf`, `docker/entrypoint.sh` (migrate, collectstatic, gunicorn)
- `.env.example`, production settings (`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, proxy SSL)
- `bootstrap_admin` management command
- GitHub Actions test workflow
- API integration tests for signing endpoint auth

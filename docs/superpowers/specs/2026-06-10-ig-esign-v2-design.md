# IG E-Sign v2 Design Spec

**Date:** 2026-06-10  
**Status:** v2 complete — Phases A, B & C shipped (teams/billing → v3)  
**Replaces / extends:** [2026-06-09-dscapi-saas-design.md](./2026-06-09-dscapi-saas-design.md) (v1 complete)

## Goal

Extend IG E-Sign beyond v1 API-only signing with richer signing audit data, per-tenant signature appearance, and an in-browser signing experience — **without payment/billing or multi-user teams in this milestone** (teams → v3).

## v1 baseline (complete)

Multi-tenant SaaS, registration, email verification, admin approval, API keys, saved certs, quotas, usage logs, portal (dashboard/keys/certs/docs), Docker deploy on `sign.incitegravity.com`.

## v2 scope

| # | Capability | Priority |
|---|------------|----------|
| A | Signing audit: document type, pre/post hashes, client IP | **P0** — security & compliance |
| B | Per-tenant signature styling | **P1** |
| C | In-browser signing UI (DocuSign-style) | **P2** — owner account only |
| — | Team invites / multi-user orgs | **→ v3** |
| — | Stripe / billing | **Deferred** |

Recommended build order: **A → B → C** (each phase shippable independently).

## v3 scope (planned)

| # | Capability |
|---|------------|
| T | Team invites / multi-user orgs (see appendix below) |
| — | Stripe / billing (when ready) |

---

## A — Signing audit trail

### Purpose

Every sign attempt (API or portal) records what was signed, cryptographic fingerprints, and origin IP for security, dispute resolution, and compliance.

### Document type (auto-detected)

**Not an API input field.** Type is inferred server-side from PDF text for analytics.

Closed enum stored on each signing event:

| Value | Detection keywords (case-insensitive, whole-word / phrase match) |
|-------|---------------------------------------------------------------------|
| `tax_invoice` | `TAX INVOICE`, `TAX INVOICE NO`, `TAX INVOICE NUMBER` |
| `purchase_order` | `PURCHASE ORDER`, `P.O.`, `PO NO`, `PO NUMBER` |
| `delivery_challan` | `DELIVERY CHALLAN`, `DELIVERY CHALLAN NO` |
| `credit_note` | `CREDIT NOTE`, `CREDIT NOTE NO` |
| `debit_note` | `DEBIT NOTE`, `DEBIT NOTE NO` |
| `proforma_invoice` | `PROFORMA INVOICE`, `PRO FORMA INVOICE` |
| `quotation` | `QUOTATION`, `QUOTE NO`, `QUOTATION NO` |
| `unknown` | No keyword matched |

**Detection algorithm (v2):**

1. Extract text from all PDF pages via PyMuPDF (`fitz`) — same library as signature placement.
2. Normalize: uppercase, collapse whitespace.
3. Scan keywords in **priority order** (longer phrases first to avoid `INVOICE` matching before `TAX INVOICE`).
4. First match wins; store enum + optional `detected_keyword` string on audit log.
5. If multiple types appear (e.g. quote header on invoice), first match in priority list wins; log `detection_confidence` = `low` when 2+ types found.

- **API:** no new request fields; detection runs automatically on decoded PDF bytes.
- **Portal (phase D):** show detected type on confirmation (read-only); optional manual override dropdown later if needed.
- **Analytics:** dashboard breakdown by `document_type` per tenant.

### Document hashes

| Field | When set | Algorithm |
|-------|----------|-----------|
| `hash_before` | Always (on decoded input PDF bytes) | SHA-256, lowercase hex (64 chars) |
| `hash_after` | Success only | SHA-256 of final signed PDF bytes |

- Hashes are of **raw file bytes**, not base64 strings.
- Failed signs still store `hash_before`; `hash_after` is null.
- Hashes are **not secrets** but must not be reversible to PDF; store for integrity proof only.
- Do **not** store full PDF content in the database.

### Client IP

| Field | Source |
|-------|--------|
| `client_ip` | `X-Forwarded-For` first hop (nginx), else `REMOTE_ADDR` |

- Record on every attempt (success and failure).
- IPv4 or IPv6 string, max 45 chars.

### Data model change

Extend **`UsageLog`** → rename display label to **Signing event** (table name can stay `accounts_usagelog` for migration simplicity):

```text
UsageLog (extended)
  tenant          FK
  endpoint        default signpdf-pfx | sign-portal (phase D)
  success         bool
  document_type   CharField choices (nullable for legacy rows; auto-detected)
  detected_keyword CharField(100) nullable
  detection_confidence CharField (high | low | none) default none
  hash_before     CharField(64) nullable
  hash_after      CharField(64) nullable
  client_ip       GenericIPAddressField nullable
  api_key         FK APIKey null (set when signed via API key)
  user            FK User null (set when signed via portal session)
  created_at      datetime
```

Quota counting unchanged: increment only on `success=True`.

### API change (non-breaking)

- No new required request fields.
- Response may include `signing_id`, `document_type` (detected), and hash prefixes for client correlation.
- Optional future: `document_type_override` for edge cases only (not in v2 initial scope).

### Portal / admin

- Dashboard activity table: document type, truncated hash prefix, IP, IST time.
- Django admin: filter by `document_type`, search by hash prefix.

---

## Appendix — Team invites / multi-user orgs (v3)

> **Deferred from v2.** v2 keeps one login per organization (registration owner). Portal signing and audit still work; `user` on audit log is always the account owner until v3.

### Purpose

Multiple users per tenant (organization) with role-based access. `TenantMembership` already exists; v3 activates it.

### Roles

| Role | Invite members | Manage API keys | Manage certs | Sign (API) | Sign (portal) | View audit log |
|------|----------------|-----------------|--------------|------------|---------------|----------------|
| **owner** | yes | yes | yes | yes | yes | yes |
| **member** | no | no | no | yes* | yes* | yes |

\*Members use tenant API keys created by owner, or portal sign (phase D) with saved certs the owner uploaded.

### Invite flow

```text
Owner → Invite email + role (member)
     → Email with accept link (72h expiry, configurable)
     → Invitee registers OR logs in if account exists
     → Accept → TenantMembership created, invite marked used
```

### Data model

```text
TenantInvite
  tenant          FK
  email           EmailField (normalized lowercase)
  role            choices (member only in v3; owner via registration)
  token           UUID unique
  invited_by      FK User
  created_at      datetime
  expires_at      datetime
  accepted_at     datetime null
```

- One pending invite per `(tenant, email)` at a time.
- Owners cannot remove the last owner without transferring ownership (v3: block delete of sole owner).

### Portal pages

- **Team** (`/dashboard/team/`): list members, pending invites, invite form (owner only).
- Session user resolves **active tenant** via primary `TenantMembership` (`is_primary=True`); v3 adds multi-member; until then one user per tenant (no org switcher).

### Auth note

API keys remain **tenant-scoped**, not user-scoped. Audit log records `api_key` or `user` to show who/what initiated the sign.

---

## B — Per-tenant signature styling ✅

### Purpose

Each tenant can customize how signatures appear on PDFs without code deploys.

### Backward compatibility

- No `TenantSignatureStyle` row, or `is_enabled=False` → **identical** to platform `settings.py` defaults.
- API clients require **no changes** until the tenant opts in via portal (**Signature** page).
- On-prem Basic Auth (no tenant) always uses platform defaults.

### Configurable fields (tenant-level defaults)

| Setting | Type | Fallback |
|---------|------|----------|
| `font_size` | int | global `SIGNATURE_FONT_SIZE` |
| `box_min_width` | int | global `SIGNATURE_BOX_MIN_WIDTH` |
| `box_height` | int | global `SIGNATURE_BOX_HEIGHT` |
| `shift_right` | int | global `SIGNATURE_BOX_SHIFT_RIGHT` |
| `shift_down` | int | global `SIGNATURE_BOX_SHIFT_DOWN_FITZ` |
| `gap_above_label` | int | global `SIGNATURE_BOX_GAP_ABOVE_LABEL` |
| `icon` | optional uploaded PNG | global green tick |
| `icon_display_width` | int | global default |
| `anchor_text` | string | `Authorised Signatory` |

### Data model

```text
TenantSignatureStyle
  tenant          OneToOne → Tenant
  ...fields above...
  updated_at      datetime
```

### Signing pipeline

`build_signing_dict()` and `signature_box_for_position()` accept a **style resolver** that merges tenant overrides over `settings` defaults.

### Portal

- **Branding / Signature** (`/dashboard/signature/`): form + live preview (static sample PDF or generated preview image).

---

## C — In-browser signing UI (DocuSign-style) ✅

### Purpose

Sign PDFs from the portal without calling the API manually — upload, review, sign, download.

### User flow

```text
1. Upload PDF (max size limit, e.g. 10 MB)
2. System auto-detects document type from PDF text (shown to user)
3. System locates anchor text "Authorised Signatory" (or tenant override)
   - If not found: show error with guidance (same as API today)
4. Select saved cert alias + enter PFX password (session-only, not stored)
5. Preview signature placement overlay
6. Sign → server-side sign (reuse pdf_signing module)
7. Download signed PDF + show signing_id / hashes in confirmation
```

### Technical approach

- **New view:** `POST /dashboard/sign/` (multipart or JSON with base64).
- **Auth:** Django session (tenant owner only in v2; members in v3).
- **Quota:** same `record_signing_usage` / audit fields as API.
- **Frontend:** PDF.js for preview; minimal custom JS (align with existing portal static assets).
- **No** persistent storage of uploaded PDFs after response (stream download, discard).

### Out of scope for v2 portal sign

- Drag-and-drop signature placement (use anchor text only, same as API).
- Multi-signer workflows / sequential signing.
- Email signed PDF to recipient.

---

## Cross-cutting

### Security

- PFX passwords never logged or persisted.
- IP extraction trusted only behind nginx (`SECURE_PROXY_SSL_HEADER` already set).
- Rate limits apply to portal sign endpoint same as login.

### Migrations

- Backfill: existing `UsageLog` rows keep null `document_type` / hashes / IP.
- No breaking change to Windows Basic Auth on-prem path (audit fields optional there).

### Testing

- Unit: hash computation, IP extraction, enum validation.
- Integration: API sign with `document_type` + hash assertions.
- Portal: in-browser sign happy path (v3: invite accept flow, member permissions).

---

## Deferred

- **v3:** Team invites / multi-user orgs (appendix above)
- Stripe / subscriptions
- Webhooks
- Per-tenant custom document types (admin UI)
- Org switcher (user in multiple tenants)
- Email delivery of signed PDFs

---

## Open decisions (need product confirmation)

1. ~~**`document_type` on API**~~ — **Resolved:** auto-detect from PDF keywords; not an API field.
2. ~~**Member API access**~~ — deferred to v3 with team invites.
3. **Portal sign quota:** count against same monthly quota as API? (assumed **yes**)
4. **Hash display in portal:** show full hash or first 8 chars + copy?
5. **Keyword list:** extend detection phrases per your real invoice templates?

---

## Success criteria

- [ ] Every successful SaaS sign has auto-detected `document_type`, `hash_before`, `hash_after`, `client_ip`.
- [ ] Tenant can set signature font/box offsets; reflected on next signed PDF.
- [ ] Account owner can upload PDF in portal, sign with saved cert, download result.
- [ ] All existing tests pass; new coverage for audit + portal sign.

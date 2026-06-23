# IG E-Sign v3 — Team Members Implementation Spec

**Date:** 2026-06-21  
**Status:** Draft — ready for implementation  
**Extends:** [2026-06-10-ig-esign-v2-design.md](./2026-06-10-ig-esign-v2-design.md) (v3 appendix)  
**Production:** `sign.incitegravity.com` — **live customers on PFX API signing and GST lookup (Pro / Pro+) must not be disrupted**

---

## 1. Goal

Allow organization **owners** to invite **team members** who can sign documents (portal and USB) under the same tenant, while keeping **one billing account**, **one quota pool**, and **unchanged API behaviour** for existing integrations.

Teams are **opt-in**. Until an owner sends an invite, every tenant continues to work exactly as today (single owner user).

---

## 2. Live production constraints (non-negotiable)

These rules apply to **every phase** of the team rollout.

### 2.1 Existing customers are owners — forever, unless they choose otherwise

| Fact today | Rule for v3 |
|------------|-------------|
| Registration creates `Tenant` + `TenantMembership(role=owner, is_primary=True)` | **No change** to registration |
| Every live paying customer is the sole user on their tenant | **No data migration** that changes `role` from `owner` to `member` |
| No customer has been invited as `member` yet | First members appear only after **explicit owner invite** |

**Do not** run a migration that demotes existing users, splits tenants, or forces re-registration.

### 2.2 PFX API signing — zero breaking changes

Endpoints (unchanged):

- `POST /api/signpdf-pfx/` — PFX / `cert_alias` signing  
- `POST /api/sign/usb/` — USB job preparation (if used via API)

| Concern | Guarantee |
|---------|-----------|
| Authentication | Still **API key only** (`dsc_live_…`). No new headers, no user login on API. |
| Request body | Same fields: `pdf_base64`, `password`, `pfx_base64` / `cert_alias`, `signature_style`, etc. |
| Saved certificates | Still tenant-scoped; `cert_alias` resolution unchanged |
| Quota | Still consumed on **`Tenant`**; Pro / Pro+ entitlements unchanged |
| Throttles | Same `THROTTLE_SIGN_PDF`, `THROTTLE_SIGN_PDF_BURST` per key/IP |
| Response shape | Same JSON (`signed_pdf_base64`, `signing_id`, hashes) |
| Audit | `api_key` set; `user` null for API calls (unchanged) |

**Team members do not get their own API keys** in v3.0. Integrations (ERP, scripts, Business Central) keep using the owner-created keys.

### 2.3 GST lookup API — zero breaking changes

Endpoints (unchanged):

- `POST /api/gst/gstin-search/`  
- `POST /api/gst/return-status/`  
- `POST /api/gst/eway-print/`, `POST /api/gst/irn-print/`, etc.

| Concern | Guarantee |
|---------|-----------|
| Authentication | API key → **tenant** (unchanged) |
| Pro / Pro+ gating | `tenant.quota_plan`, `QuotaEntitlement`, GST profile checks unchanged |
| GST quota | `gst_monthly_quota` / `gst_usage_this_month` on **tenant** (unchanged) |
| Throttles | `THROTTLE_GST_LOOKUP`, `THROTTLE_GST_LOOKUP_BURST` unchanged |
| Portal GST try | Stays **owner-only** (already stricter than member matrix) |

### 2.4 Pro / Pro+ entitlements

- Entitlements remain on **`Tenant`** and **`QuotaEntitlement`** — not per-user.  
- Adding members **does not** create new tenants, new plans, or new billing rows.  
- Member portal/USB signs **consume the same org signing quota** as the owner.  
- Admin grant/extend Pro flows in Django admin **unchanged**.

### 2.5 URLs, keys, certs, agents

| Asset | Rule |
|-------|------|
| API keys | Existing keys keep working; no forced rotation |
| Saved PFX (`StoredCertificate`) | Unchanged; members use owner-uploaded certs in portal only |
| USB paired agents | Unchanged; pairing/revoke stays **owner-only** |
| Dashboard URLs | Existing paths unchanged; **new** `/dashboard/team/` only |

### 2.6 Feature flag (recommended)

```env
# Default false until T2 is tested on staging; owners-only behaviour when false.
TEAMS_ENABLED=false
```

When `TEAMS_ENABLED=false`:

- Hide Team nav and invite UI  
- Reject invite accept URLs with friendly message  
- All other behaviour identical to today (owners already have full access)

When `true`, enable invite flow. **RBAC decorators** (owner vs member) may ship in T1 even with flag off — they only affect users with `role=member`, of which there are none in production until invites go out.

---

## 3. Current state vs target

### Already implemented (security pass)

- `TenantMembership` + `MembershipRole` (`owner` / `member`)  
- `primary_tenant_required` — users without membership redirected safely  
- `tenant_owner_required` / `tenant_owner_only` on destructive portal actions  
- Tests: member blocked from API keys and certs pages  
- Portal + USB sign allowed for any active tenant member  
- GST portal try: owner-only  
- Audit: portal signs record `user` (member or owner)

### Not implemented

- `TenantInvite` model and email flow  
- `/dashboard/team/` UI  
- Remove member / transfer ownership  
- Nav hidden by role  
- Member-visible audit (dashboard activity vs owner-only usage report)  
- Documentation for customers  

### Doc drift to fix when shipping

- `docs/SECURITY-AUDIT.md` M11 — update to reflect partial RBAC (not “never enforced”)  
- v2 appendix note “audit user is always owner until v3” — **obsolete** for portal sign

---

## 4. Roles and permissions

### 4.1 Permission matrix (target)

| Action | Owner | Member |
|--------|:-----:|:------:|
| **API** `POST /api/signpdf-pfx/` (via integration key) | — | — |
| **API** GST endpoints (via integration key) | — | — |
| View dashboard | yes | yes |
| View recent activity (last 20 signs) | yes | yes |
| Usage report + CSV/PDF export | yes | no |
| Create / revoke API keys | yes | no |
| Upload / delete saved PFX certs | yes | no |
| Company profile + NIC credentials | yes | no |
| Create / edit / delete signature styles | yes | no |
| View signature styles (read-only) | yes | yes |
| Portal sign (PFX password per session) | yes | yes |
| USB sign (portal) | yes | yes |
| USB agent page + download installer | yes | yes |
| Generate pairing code / revoke agent | yes | no |
| GST portal try | yes | no |
| API docs page | yes | yes |
| Invite / remove team members | yes | no |
| Register new organization | yes* | yes* |

\*Registration always creates a **new** tenant as **owner**. Invite accept joins an **existing** tenant as **member** (see §5).

**API rows:** Members do not use the API through the portal. If they possess an API key string, it still works (tenant-scoped secret) — document as owner responsibility.

### 4.2 Quota and billing (shared org)

```
Tenant (Pro / Pro+)
├── monthly_quota / usage_this_month  OR  QuotaEntitlement
├── gst_monthly_quota / gst_usage_this_month
├── APIKey(s)          ← owner manages
├── StoredCertificate(s) ← owner manages
├── Owner user         ← full admin
└── Member user(s)     ← sign only; shares quota
```

---

## 5. Data model

### 5.1 Existing — no schema change required for T1

```text
TenantMembership
  tenant       FK Tenant
  user         FK User
  role         owner | member   (default owner)
  is_primary   bool             (default True)
  unique (tenant, user)
```

**Production backfill (safe, idempotent):**

```sql
-- Ensure every membership is owner if role was ever null (should not happen)
UPDATE accounts_tenantmembership SET role = 'owner' WHERE role IS NULL OR role = '';
```

No change to `Tenant`, `APIKey`, `StoredCertificate`, `QuotaEntitlement`.

### 5.2 New — T2 only

```text
TenantInvite
  id              UUID PK
  tenant          FK Tenant
  email           EmailField (normalized lowercase, indexed)
  role            choices — member only in v3.0
  token           UUID unique, indexed
  invited_by      FK User
  created_at      datetime
  expires_at      datetime
  accepted_at     datetime null
  revoked_at      datetime null

  constraints:
    - One pending invite per (tenant, email) where accepted_at IS NULL AND revoked_at IS NULL
```

**Indexes:** `(tenant, email)`, `token`

---

## 6. User flows

### 6.1 Unchanged — new organization (today’s customers)

```
/register/ → verify email → admin approval → owner logs in → full access
```

No new steps. No team UI required.

### 6.2 New — invite member (T2, TEAMS_ENABLED=true)

```
Owner → /dashboard/team/ → enter email → TenantInvite created → email sent
     → /invite/<token>/ 
         → if not logged in: register OR login (existing account)
         → accept → TenantMembership(member, is_primary=True) 
         → invite.accepted_at set
         → redirect dashboard
```

### 6.3 Invite accept rules (avoid breaking live users)

| Scenario | Behaviour |
|----------|-----------|
| Email already **owner** of another tenant | **Reject** with message: “You already have an organization. Contact support to transfer or use a different email.” (v3.0 — no multi-org) |
| Email already **member** of this tenant | Idempotent: show “Already a member” |
| Email has account, not in any tenant | Allow login → accept → member |
| Email new | Short registration (password only; **no new tenant**) → accept → member |
| Invite expired | 403 + “Ask owner to resend” |
| `TEAMS_ENABLED=false` | 404 or “Teams not available yet” |

**Critical:** Invite registration path must **not** call `register_tenant()` — it must only create `User` + `TenantMembership` on the **inviting** tenant.

### 6.4 Remove member (T1/T2)

- Owner removes member → delete `TenantMembership` (user account remains)  
- Cannot remove last owner  
- Cannot remove self if sole owner  
- Removed member loses portal access; API keys they memorized still work (owner should revoke keys if offboarding integrator — document only)

---

## 7. Implementation phases

### Phase T1 — RBAC completion + Team page (no email)

**Ship first. Safe for production.**

| Task | Notes |
|------|--------|
| `/dashboard/team/` (owner only) | List `TenantMembership` for tenant |
| Role badges in UI | owner / member |
| Remove member (POST) | Block last owner |
| Nav by role | Hide Keys, Certs, Company, Usage report, Team (for members) |
| Audit tests | Matrix: every portal route × owner/member |
| Member dashboard | Show activity table; link to Sign / USB / Docs |
| Optional: `TEAMS_ENABLED` | Hide team page until T2 if desired |

**Explicitly out of T1:** email, `TenantInvite`, registration changes

**Production impact:** **None** for existing customers (all owners).

### Phase T2 — Invite flow

| Task | Notes |
|------|--------|
| `TenantInvite` migration | Additive only |
| Invite form on team page | Owner enters email |
| Email template | Accept link, 72h expiry (`TEAM_INVITE_HOURS=72`) |
| `/invite/<token>/` views | Accept + register-without-tenant |
| Rate limit | `ratelimit:team_invite` per owner IP |
| `TEAMS_ENABLED=true` on staging → production | After QA |

**Production impact:** **Opt-in** — only tenants that invite are affected.

### Phase T3 — Polish

| Task | Notes |
|------|--------|
| Resend / revoke pending invite | Owner actions |
| Ownership transfer | Optional v3.1 if needed |
| Dashboard “Signed by {email}” for members | Audit already has `user` |
| Member read-only usage snippet | Count only, no export |
| Customer docs + API docs note | “Teams are portal-only; API is org-scoped” |
| Update SECURITY-AUDIT.md M11 | Mark remediated |

**Shipped:** Resend/revoke on Team page; member usage snippet on dashboard; `docs/TEAM-MEMBERS.md`; API docs team section; M11/M12 audit updates. Ownership transfer deferred to v3.1.

---

## 8. API and integration compatibility checklist

Before each production deploy, verify with a **real Pro tenant** (staging mirror):

- [ ] `POST /api/signpdf-pfx/` with `cert_alias` — 200, quota decrements  
- [ ] `POST /api/signpdf-pfx/` with `pfx_base64` — 200  
- [ ] GST GSTIN search — 200 on Pro tenant  
- [ ] GST e-way / IRN print — 200 when profile complete  
- [ ] Revoked key still 401  
- [ ] Quota exceeded still 429 with same message  
- [ ] Existing API key prefix unchanged in DB  
- [ ] No new required env vars without defaults (except optional `TEAMS_ENABLED`)

---

## 9. Rollout plan (production)

| Step | Action |
|------|--------|
| 1 | Deploy **T1** to production — no flag change |
| 2 | Smoke test owner flows (sign, GST API, keys) on Pro account |
| 3 | Internal dogfood: create **test** tenant, add test member via admin/SQL |
| 4 | Deploy **T2** with `TEAMS_ENABLED=false` |
| 5 | Staging: full invite flow + member sign + API unchanged on same tenant |
| 6 | Enable `TEAMS_ENABLED=true` on staging → one pilot customer |
| 7 | Production: `TEAMS_ENABLED=true`; announce Team feature to owners only |
| 8 | Monitor: 400/429 rates, quota consumption, support tickets |

**Rollback:** Set `TEAMS_ENABLED=false`. Members already created retain access unless manually removed — document support procedure.

---

## 10. Testing requirements

### Unit / integration

- `PortalSecurityTests` extended to full matrix (§4.1)  
- Invite accept does not create second `Tenant`  
- Invite accept rejects existing owner of another org  
- Member portal sign creates `UsageLog.user = member`  
- Member USB sign same  
- API sign with tenant key: **no** `user` on log (unchanged)  
- GST API on Pro tenant before/after adding member: identical behaviour  

### Manual (Pro customer scenario)

1. Owner on Pro+ signs via API with `cert_alias` — success  
2. Owner invites accountant as member  
3. Member signs invoice in portal — success, quota -1 on **same** tenant  
4. Member cannot open `/dashboard/keys/`  
5. Owner’s ERP integration still signs via same API key — success  
6. GST lookup via API — success, `gst_usage_this_month` increments  

---

## 11. Success criteria

- [ ] **Zero** regression for single-owner Pro/Pro+ tenants (default case)  
- [ ] PFX API and GST API unchanged for integrators  
- [ ] Owner can invite ≥1 member without support intervention  
- [ ] Member can portal + USB sign using org certs  
- [ ] Owner retains exclusive control of keys, certs, agents, billing-related settings  
- [ ] Audit shows which portal user signed  

---

## 12. Out of scope (v3.0)

- Per-member API keys or per-member quotas  
- Stripe / self-serve billing  
- Multi-org per user (org switcher)  
- Member-managed GST profile or NIC credentials  
- SSO / SAML  
- Fine-grained custom roles (viewer, signer, admin)  

---

## 13. Environment variables (new, all optional)

| Variable | Default | Purpose |
|----------|---------|---------|
| `TEAMS_ENABLED` | `false` | Gate invite UI and accept URLs |
| `TEAM_INVITE_HOURS` | `72` | Invite link expiry |

**No changes** required to existing production vars for PFX/GST (`THROTTLE_*`, `SIGNATURE_MAX_SLOTS`, `ENCRYPTION_KEY`, etc.).

---

## 14. References

- Role appendix (original): [2026-06-10-ig-esign-v2-design.md § Team invites](./2026-06-10-ig-esign-v2-design.md)  
- RBAC implementation: `accounts/decorators.py`, `accounts/services.user_is_tenant_owner`  
- Quota: `accounts/quota.py`, `accounts/models.QuotaEntitlement`  
- API signing: `signPdf/views.py`, `usb_agent/tenant_api_views.py`  
- GST API: `gst/api_views.py`  

---

## 15. Summary for stakeholders

**Existing live customers (PFX API + GST Pro/Pro+):**  
Nothing changes until they **choose** to invite teammates. Same API keys, same endpoints, same quotas, same certificates, same agents.

**Teams add** optional portal users who can sign on behalf of the organization under the owner’s governance — without splitting billing or integrations.

# Azure Container Apps — IG E-Sign cutover guide

Migrate from the dedicated Linux VM (`docker-compose.host-nginx.yml` + host nginx) to:

| Piece | Azure service |
|-------|----------------|
| App image | **Azure Container Registry (ACR)** |
| Web / API | **Azure Container Apps** (`min replicas = 1`, `max = 1`) |
| Database | **Azure Database for PostgreSQL Flexible Server** |
| TLS + domain | Container Apps managed certificate for `sign.incitegravity.com` |

Target load: ~1000 API hits/day, 24×7 (always-on with `minReplicas=1`).

---

## Prerequisites

On your laptop (or CI):

- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) (`az`)
- Docker with buildx
- `psql` + `gzip` (for restore)
- `az login` and a subscription with permission to create resources

On the current VM:

- Running stack under `/opt/dscapi`
- Ability to run `docker compose … exec db pg_dump`

Copy scripts are in this folder:

```text
deploy/azure/
  README.md                 ← cutover guide
  BACKUP.md                 ← backup & disaster recovery
  env.azure.example         ← env template for Container App
  01-create-resources.sh
  02-build-push.sh
  03-deploy-app.sh
  04-db-dump-restore.sh     ← VM migration dump/restore
  05-backup-db.sh           ← scheduled pg_dump (+ optional Blob)
  06-restore-db.sh          ← restore from dump or Blob
  backups/                  ← local dumps (gitignored)
```

```bash
chmod +x deploy/azure/*.sh
```

---

## Architecture (after cutover)

```text
Internet
   │
   ▼
DNS: sign.incitegravity.com  →  Container Apps ingress (HTTPS)
   │
   ▼
Container App  dscapi:latest  (Gunicorn :8000, min=1)
   │
   ▼
Azure PostgreSQL Flexible Server  (sslmode=require)
```

Host nginx/certbot on the VM are **not** used after cutover. Container Apps terminates TLS.

---

## Phase 0 — Plan the maintenance window

1. Pick a short window (15–30 min) for final DB dump + DNS change.
2. Notify users if needed (signing / agent briefly unavailable).
3. Keep the VM running until Azure is verified — easy rollback = point DNS back to the VM.

---

## Phase 1 — Create Azure resources

```bash
az login
az account set --subscription "YOUR_SUBSCRIPTION_NAME"

export AZ_LOCATION=centralindia          # pick your region
export AZ_RG=rg-ig-esign
export AZ_PREFIX=igesign                 # short, globally unique for ACR/PG names
export PG_ADMIN_PASSWORD='ChooseAStrongPassword!'

./deploy/azure/01-create-resources.sh
```

This creates:

- Resource group  
- Log Analytics  
- ACR (Basic)  
- Container Apps Environment  
- PostgreSQL Flexible Server (**B1ms**, DB `dscapi`, user `dscapi`)  

Script prints `DATABASE_URL`. **URL-encode** the password if it contains `@`, `#`, `%`, etc.

> First create uses a wide Postgres firewall for easy restore/cutover. Tighten it after go-live (see Phase 7).

---

## Phase 2 — Build and push the image

From the **repo root** on your Mac/CI:

```bash
export AZ_RG=rg-ig-esign
export ACR_NAME=igesignacr          # same as ${AZ_PREFIX}acr from step 1

./deploy/azure/02-build-push.sh
# note the printed IMAGE_TAG
export IMAGE_TAG=igesignacr.azurecr.io/dscapi:YYYYMMDDHHMM
```

---

## Phase 3 — Prepare Container App environment file

```bash
cp deploy/azure/env.azure.example deploy/azure/.env.azure
# edit deploy/azure/.env.azure — use the SAME SECRET_KEY / ENCRYPTION_KEY
# as production VM if you are migrating live data (required for decrypting stored secrets)
```

Critical:

| Variable | Notes |
|----------|--------|
| `DATABASE_URL` | Azure PG host + `?sslmode=require` |
| `SECRET_KEY` | Prefer **same as VM** during migration |
| `ENCRYPTION_KEY` | **Must match VM** or encrypted tenant data breaks |
| `ALLOWED_HOSTS` | Domain; later add ACA default FQDN for smoke test |
| `SITE_URL` / `CSRF_TRUSTED_ORIGINS` | `https://sign.incitegravity.com` |
| GST / SMTP | Copy from VM `/opt/dscapi/.env` |

Do **not** commit `.env.azure`.

---

## Phase 4 — First deploy (smoke test URL)

Deploy before or after DB restore (migrate on start is idempotent).

```bash
export AZ_RG=rg-ig-esign
export AZ_PREFIX=igesign
export IMAGE_TAG=...                  # from phase 2
export ENV_FILE=deploy/azure/.env.azure

./deploy/azure/03-deploy-app.sh
```

Script prints the default hostname, e.g. `igesign-web.xxxxx.azurecontainerapps.io`.

1. Add that host to `ALLOWED_HOSTS` and `https://…` to `CSRF_TRUSTED_ORIGINS` in `.env.azure`.
2. Re-run `03-deploy-app.sh`.
3. Open `https://<aca-fqdn>/` — expect portal HTML (DB may still be empty until restore).

```bash
az containerapp logs show -n igesign-web -g rg-ig-esign --follow
```

---

## Phase 5 — Migrate PostgreSQL data (VM → Azure)

### 5a. Dump on the VM

```bash
cd /opt/dscapi
# copy 04-db-dump-restore.sh to the VM, or run the docker compose one-liner:

docker compose -f docker-compose.host-nginx.yml exec -T db \
  pg_dump -U dscapi -d dscapi --no-owner --no-acl \
  | gzip > /tmp/dscapi-dump.sql.gz

ls -lh /tmp/dscapi-dump.sql.gz
```

Copy dump to your laptop:

```bash
scp ig_signuser@YOUR_VM_IP:/tmp/dscapi-dump.sql.gz ~/Downloads/
```

### 5b. Maintenance + final dump (cutover)

Near go-live:

1. Optionally stop accepting traffic on the VM (nginx maintenance or stop `web` container) so the dump is final.
2. Re-run dump (5a) for a fresh file.
3. Restore to Azure (5c).
4. Point DNS (Phase 6).

### 5c. Restore into Azure Postgres

Allow your public IP on the Flexible Server firewall (Portal → Networking), then:

```bash
export AZURE_PG_HOST=igesign-pg.postgres.database.azure.com
export AZURE_PG_USER=dscapi
export AZURE_PG_PASSWORD='...'
export AZURE_PG_DB=dscapi

# If Container App already ran migrate into an empty DB, reset schema once:
export AZURE_PG_RESET_SCHEMA=true

./deploy/azure/04-db-dump-restore.sh restore ~/Downloads/dscapi-dump.sql.gz
```

Restart the app so connections refresh:

```bash
az containerapp revision restart -n igesign-web -g rg-ig-esign --revision <latest-revision>
# or:
az containerapp update -n igesign-web -g rg-ig-esign --min-replicas 1
```

Smoke-test on the ACA URL: login, dashboard, one sign, USB agent status if used.

---

## Phase 6 — Custom domain + DNS cutover

### 6a. Bind domain on Container Apps

Portal: Container App → **Custom domains** → add `sign.incitegravity.com` → follow validation (TXT/CNAME as shown) → enable **managed certificate**.

Or CLI (names vary by API version; Portal is fine):

```bash
# Example pattern — confirm with current az containerapp docs for your CLI version
az containerapp hostname add \
  --hostname sign.incitegravity.com \
  --name igesign-web \
  --resource-group rg-ig-esign
```

### 6b. DNS

At your DNS provider, change `sign.incitegravity.com`:

- Usually **CNAME** to the Container App FQDN, **or** the record type Azure shows in the custom domain blade.

Lower TTL (e.g. 60–300s) a day before cutover.

### 6c. Env after domain is live

Set back to production-only hosts (optional to keep ACA FQDN for debugging):

```env
ALLOWED_HOSTS=sign.incitegravity.com
CSRF_TRUSTED_ORIGINS=https://sign.incitegravity.com
SITE_URL=https://sign.incitegravity.com
```

Re-run `03-deploy-app.sh`.

### 6d. Verify on the real domain

- [ ] `https://sign.incitegravity.com/` loads  
- [ ] Login / register email  
- [ ] `/admin/` (note: VM nginx IP allowlist is gone — protect admin via Azure / App restrictions or IP filter if needed)  
- [ ] Sign PDF + USB agent pairing/heartbeat  
- [ ] GST try (if configured)  

---

## Phase 7 — Harden and decommission VM

1. **Postgres firewall:** remove `0.0.0.0–255.255.255.255`; allow only required sources or move Flexible Server + Container Apps onto a VNet.  
2. **Admin:** Container Apps has no nginx `/admin/` IP ACL — add authentication, Azure Front Door WAF, or restrict by IP at the edge if you need the old model.  
3. Keep the VM powered on 3–7 days as rollback.  
4. Then stop Compose / deallocate VM when confident.

Rollback: point DNS A/CNAME back to the VM; start `docker compose -f docker-compose.host-nginx.yml up -d` if stopped. DB may have diverged after cutover — only roll back if you have not taken important new writes, or restore a pre-cutover dump to the VM.

---

## Day-2 operations

See **[BACKUP.md](./BACKUP.md)** for Postgres backups, Blob storage, and restore runbooks.

### Redeploy a new image

```bash
./deploy/azure/02-build-push.sh
export IMAGE_TAG=...
export ENV_FILE=deploy/azure/.env.azure
./deploy/azure/03-deploy-app.sh
```

### Logs

```bash
az containerapp logs show -n igesign-web -g rg-ig-esign --follow
```

### Scale

Already set: `min=1`, `max=1`, 0.5 vCPU / 1 GiB. Raise max replicas later if signing latency grows.

### Secrets

Prefer updating via:

```bash
az containerapp secret set -n igesign-web -g rg-ig-esign --secrets database-url='postgres://...'
```

then refresh env to `secretref:…`.

---

## Cost checklist (starting point)

| Resource | Suggested SKU |
|----------|----------------|
| Container App | 0.5 vCPU / 1 GiB, min 1 |
| PostgreSQL | Burstable **B1ms**, 32 GB |
| ACR | **Basic** |
| Log Analytics | Pay-as-you-go (low volume) |

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `DisallowedHost` | Add ACA FQDN / custom domain to `ALLOWED_HOSTS` |
| CSRF failures | `CSRF_TRUSTED_ORIGINS` must include `https://…` |
| DB connection errors | `?sslmode=require`, firewall, URL-encoded password |
| Decryption / cert errors after migrate | `ENCRYPTION_KEY` must match VM |
| 502 / app not starting | `az containerapp logs show` — migrate/SMTP/GST config |
| Cold starts | Ensure `--min-replicas 1` |

---

## What this does *not* change

- Microsoft Store agent install path  
- Tenant data model / API contracts  
- Need for SMTP + GST partner credentials on the server  

USB agents keep using `SITE_URL` / pairing against `https://sign.incitegravity.com` after DNS cutover — no agent reinstall if the domain stays the same.

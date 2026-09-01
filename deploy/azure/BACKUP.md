# Backup & disaster recovery — Azure (IG E-Sign)

Production stack:

| Component | Name (example) | Backup priority |
|-----------|----------------|-----------------|
| PostgreSQL | `igesign-pg` | **Critical** |
| Secrets / env | `deploy/azure/.env.azure` | **Critical** (`ENCRYPTION_KEY`!) |
| Container image | `igesignacr.azurecr.io/dscapi:*` | High |
| Container App config | `igesign-web` | Medium (recreate from `.env.azure`) |
| Log Analytics | `igesign-logs` | Low |
| DNS | GoDaddy / registrar | Document only |

The Container App is **stateless**. Protect **Postgres + secrets + image tags**.

---

## Phase 1 — Enable now

### 1. PostgreSQL automated backups (Azure PITR)

Portal → **Azure Database for PostgreSQL flexible server** → `igesign-pg` → **Backup and restore**

- Set **retention** to at least **7 days** (14–35 if budget allows)
- Enable **geo-redundant backup** if you need region-level DR
- Quarterly: **Restore** to a new server name and smoke-test login

PITR is your fastest recovery for “oops” deletes or bad migrations.

### 2. Offline secrets backup

Store an **encrypted** copy of `deploy/azure/.env.azure` in a password manager or company vault.

Must include:

- `ENCRYPTION_KEY` — without it, encrypted tenant data is lost forever
- `SECRET_KEY`, `DATABASE_URL`, SMTP, GST credentials

Update the vault copy whenever you rotate secrets.

### 3. Scheduled logical backups (`05-backup-db.sh`)

Weekly minimum; daily recommended for production.

```bash
export ENV_FILE=deploy/azure/.env.azure
./deploy/azure/05-backup-db.sh
```

Output: `deploy/azure/backups/dscapi-YYYYMMDD-HHMMSS.sql.gz` (gitignored)

**Cron example** (Mac/Linux, Sunday 02:30 IST):

```cron
30 2 * * 0 cd /path/to/NSSIApi && ENV_FILE=deploy/azure/.env.azure ./deploy/azure/05-backup-db.sh >> /var/log/dscapi-backup.log 2>&1
```

Ensure your runner’s IP is allowed on Postgres firewall, or run from Azure Automation / a small VM in Azure.

### 4. Azure Blob off-site copy (recommended)

One-time setup:

```bash
export AZ_RG=rg-ig-esign
export AZ_LOCATION=centralindia
export AZURE_BACKUP_STORAGE_ACCOUNT=igesignbackups   # globally unique, lowercase
export AZURE_BACKUP_CONTAINER=dscapi-db

az storage account create \
  -g "${AZ_RG}" -n "${AZURE_BACKUP_STORAGE_ACCOUNT}" \
  -l "${AZ_LOCATION}" --sku Standard_LRS --kind StorageV2

az storage container create \
  --account-name "${AZURE_BACKUP_STORAGE_ACCOUNT}" \
  --name "${AZURE_BACKUP_CONTAINER}" \
  --auth-mode login

# Soft delete (portal: Storage account → Data protection)
# Enable blob soft delete + versioning, retention 30 days
```

Upload on each backup:

```bash
export ENV_FILE=deploy/azure/.env.azure
export AZURE_BACKUP_STORAGE_ACCOUNT=igesignbackups
export AZURE_BACKUP_CONTAINER=dscapi-db
./deploy/azure/05-backup-db.sh
```

### 5. Pin known-good image tags

After each successful deploy, record the tag from `02-build-push.sh`:

```text
igesignacr.azurecr.io/dscapi:202608311430
```

ACR → **Retention** — keep at least the last 5 tags.

---

## Phase 2 — Stronger DR (within a month)

- Move secrets to **Azure Key Vault** (Container App secret references)
- Alerts: Postgres storage %, Container App restart count, HTTP 5xx
- Quarterly restore drill using `06-restore-db.sh` on a **new** Postgres server
- Decommission old VM only after backups are verified

---

## Restore runbooks

### A — Bad deploy (database OK)

```bash
export IMAGE_TAG=igesignacr.azurecr.io/dscapi:PREVIOUS_GOOD_TAG
export ENV_FILE=deploy/azure/.env.azure
./deploy/azure/03-deploy-app.sh
```

Or Portal → `igesign-web` → **Revisions** → activate previous revision.

### B — Database restore from pg_dump

**Option 1 — overwrite existing DB** (maintenance window, downtime):

```bash
export ENV_FILE=deploy/azure/.env.azure
export AZURE_PG_RESET_SCHEMA=true
./deploy/azure/06-restore-db.sh deploy/azure/backups/dscapi-YYYYMMDD-HHMMSS.sql.gz

# Restart app
REV=$(az containerapp revision list -n igesign-web -g rg-ig-esign --query "[?properties.active].name | [0]" -o tsv)
az containerapp revision restart -n igesign-web -g rg-ig-esign --revision "$REV"
```

**Option 2 — safer: new Postgres server** (Portal → Restore / create new server):

1. Create `igesign-pg-restored` (or restore from Azure PITR)
2. Update `DATABASE_URL` in `.env.azure`
3. `./deploy/azure/03-deploy-app.sh`
4. Smoke-test, then cut over (no DNS change needed)

### C — Restore from Blob

```bash
export AZURE_BACKUP_STORAGE_ACCOUNT=igesignbackups
export AZURE_BACKUP_CONTAINER=dscapi-db
export AZURE_BACKUP_BLOB=dscapi/2026/08/31/dscapi-20260831-023000.sql.gz
export ENV_FILE=deploy/azure/.env.azure
export AZURE_PG_RESET_SCHEMA=true

./deploy/azure/06-restore-db.sh --from-blob
```

### D — Full region disaster

1. Create new RG + Postgres + ACR + Container Apps in another region (run `01`–`03` with new names)
2. Restore DB from geo-redundant backup or latest blob dump
3. Deploy image from ACR (geo-replication) or rebuild with `02-build-push.sh`
4. Apply saved `.env.azure`, redeploy `03`
5. Rebind `sign.incitegravity.com` + DNS

---

## Scripts

| Script | Purpose |
|--------|---------|
| `05-backup-db.sh` | `pg_dump` → local `.sql.gz`, optional Blob upload |
| `06-restore-db.sh` | Restore `.sql.gz` (or `--from-blob`) |
| `04-db-dump-restore.sh` | Legacy VM Docker → Azure migration |

---

## Retention targets

| Backup type | Frequency | Retention |
|-------------|-----------|-----------|
| Azure Postgres PITR | Continuous | 7–35 days |
| `pg_dump` (local) | Daily/weekly | 14 days (`BACKUP_KEEP_LOCAL`) |
| `pg_dump` (Blob) | Daily/weekly | 30–90 days |
| `.env.azure` vault | On change | Indefinite |
| ACR image tags | Per deploy | Last 5 tags |

---

## RTO / RPO (realistic)

| Metric | Target |
|--------|--------|
| **RPO** (max data loss) | 24h with weekly dump; ~minutes with daily dump + PITR |
| **RTO** (time to restore) | 1–4 hours manual |

---

## Checklist after go-live

- [ ] Postgres backup retention verified in Portal
- [ ] `.env.azure` saved in encrypted vault
- [ ] First manual `05-backup-db.sh` succeeded
- [ ] Blob storage created (optional but recommended)
- [ ] Restore test to a **new** server completed once
- [ ] Last 3 good `IMAGE_TAG` values documented
- [ ] DNS / resource names documented for on-call

#!/usr/bin/env bash
# Logical backup of Azure PostgreSQL Flexible Server (pg_dump).
#
# Prerequisites:
#   - psql/pg_dump installed locally
#   - Your IP allowed on Postgres firewall (or run from Azure Cloud Shell)
#   - az login (optional, for blob upload)
#
# Usage:
#   export ENV_FILE=deploy/azure/.env.azure
#   ./deploy/azure/05-backup-db.sh
#
# Custom output path:
#   ./deploy/azure/05-backup-db.sh /tmp/dscapi-20260831.sql.gz
#
# Upload to Azure Blob (optional — set these first):
#   export AZURE_BACKUP_STORAGE_ACCOUNT=igesignbackups
#   export AZURE_BACKUP_CONTAINER=dscapi-db
#   ./deploy/azure/05-backup-db.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT}/deploy/azure/.env.azure}"
BACKUP_DIR="${BACKUP_DIR:-${ROOT}/deploy/azure/backups}"
TS="$(date +%Y%m%d-%H%M%S)"
OUT_FILE="${1:-${BACKUP_DIR}/dscapi-${TS}.sql.gz}"

load_database_url() {
  if [[ -n "${DATABASE_URL:-}" ]]; then
    return
  fi
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Set DATABASE_URL or ENV_FILE (${ENV_FILE} not found)" >&2
    exit 1
  fi
  local line key val
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
    [[ "${line}" != *=* ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ "${key}" == "DATABASE_URL" ]] && DATABASE_URL="${val}" && break
  done < "${ENV_FILE}"
  : "${DATABASE_URL:?DATABASE_URL not found in ${ENV_FILE}}"
}

require_pg_tools() {
  command -v pg_dump >/dev/null 2>&1 || {
    echo "pg_dump not found. Install PostgreSQL client tools." >&2
    exit 1
  }
}

upload_to_blob() {
  local file="$1"
  : "${AZURE_BACKUP_STORAGE_ACCOUNT:?Set AZURE_BACKUP_STORAGE_ACCOUNT for blob upload}"
  : "${AZURE_BACKUP_CONTAINER:?Set AZURE_BACKUP_CONTAINER for blob upload}"

  local blob_name="dscapi/$(date +%Y/%m/%d)/$(basename "${file}")"
  echo "==> Uploading to blob ${AZURE_BACKUP_STORAGE_ACCOUNT}/${AZURE_BACKUP_CONTAINER}/${blob_name}"

  if [[ -n "${AZURE_BACKUP_STORAGE_KEY:-}" ]]; then
    az storage blob upload \
      --account-name "${AZURE_BACKUP_STORAGE_ACCOUNT}" \
      --account-key "${AZURE_BACKUP_STORAGE_KEY}" \
      --container-name "${AZURE_BACKUP_CONTAINER}" \
      --name "${blob_name}" \
      --file "${file}" \
      --overwrite false \
      --output none
  else
    az storage blob upload \
      --account-name "${AZURE_BACKUP_STORAGE_ACCOUNT}" \
      --container-name "${AZURE_BACKUP_CONTAINER}" \
      --name "${blob_name}" \
      --file "${file}" \
      --auth-mode login \
      --overwrite false \
      --output none
  fi

  echo "Uploaded: https://${AZURE_BACKUP_STORAGE_ACCOUNT}.blob.core.windows.net/${AZURE_BACKUP_CONTAINER}/${blob_name}"
}

prune_local_backups() {
  local keep="${BACKUP_KEEP_LOCAL:-14}"
  [[ "${keep}" -le 0 ]] && return
  if [[ -d "${BACKUP_DIR}" ]]; then
    find "${BACKUP_DIR}" -maxdepth 1 -name 'dscapi-*.sql.gz' -type f -mtime +"${keep}" -print -delete 2>/dev/null || true
  fi
}

load_database_url
require_pg_tools
mkdir -p "$(dirname "${OUT_FILE}")"

echo "==> Dumping Azure Postgres → ${OUT_FILE}"
pg_dump "${DATABASE_URL}" --no-owner --no-acl | gzip > "${OUT_FILE}"
ls -lh "${OUT_FILE}"

if [[ -n "${AZURE_BACKUP_STORAGE_ACCOUNT:-}" ]]; then
  upload_to_blob "${OUT_FILE}"
fi

prune_local_backups
echo "Backup complete."

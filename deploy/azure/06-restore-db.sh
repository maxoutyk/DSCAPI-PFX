#!/usr/bin/env bash
# Restore a logical pg_dump (.sql.gz) into Azure PostgreSQL Flexible Server.
#
# WARNING: Destructive when AZURE_PG_RESET_SCHEMA=true (drops public schema first).
# Prefer restoring to a NEW server for disaster tests, then point DATABASE_URL at it.
#
# Usage:
#   export ENV_FILE=deploy/azure/.env.azure
#   export AZURE_PG_RESET_SCHEMA=true   # only when overwriting existing DB
#   ./deploy/azure/06-restore-db.sh deploy/azure/backups/dscapi-20260831-120000.sql.gz
#
# Download from blob then restore:
#   export AZURE_BACKUP_STORAGE_ACCOUNT=igesignbackups
#   export AZURE_BACKUP_CONTAINER=dscapi-db
#   export AZURE_BACKUP_BLOB=dscapi/2026/08/31/dscapi-20260831-120000.sql.gz
#   ./deploy/azure/06-restore-db.sh --from-blob

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT}/deploy/azure/.env.azure}"

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

download_from_blob() {
  : "${AZURE_BACKUP_STORAGE_ACCOUNT:?Set AZURE_BACKUP_STORAGE_ACCOUNT}"
  : "${AZURE_BACKUP_CONTAINER:?Set AZURE_BACKUP_CONTAINER}"
  : "${AZURE_BACKUP_BLOB:?Set AZURE_BACKUP_BLOB (path inside container)}"

  local dest="${1:?}"
  mkdir -p "$(dirname "${dest}")"
  echo "==> Downloading blob ${AZURE_BACKUP_BLOB}"

  if [[ -n "${AZURE_BACKUP_STORAGE_KEY:-}" ]]; then
    az storage blob download \
      --account-name "${AZURE_BACKUP_STORAGE_ACCOUNT}" \
      --account-key "${AZURE_BACKUP_STORAGE_KEY}" \
      --container-name "${AZURE_BACKUP_CONTAINER}" \
      --name "${AZURE_BACKUP_BLOB}" \
      --file "${dest}" \
      --output none
  else
    az storage blob download \
      --account-name "${AZURE_BACKUP_STORAGE_ACCOUNT}" \
      --container-name "${AZURE_BACKUP_CONTAINER}" \
      --name "${AZURE_BACKUP_BLOB}" \
      --file "${dest}" \
      --auth-mode login \
      --output none
  fi
}

require_psql() {
  command -v psql >/dev/null 2>&1 || {
    echo "psql not found. Install PostgreSQL client tools." >&2
    exit 1
  }
}

restore_dump() {
  local dump_file="$1"
  if [[ ! -f "${dump_file}" ]]; then
    echo "Missing dump file: ${dump_file}" >&2
    exit 1
  fi

  load_database_url
  require_psql

  echo "==> Restoring ${dump_file}"
  echo "    Target: (from DATABASE_URL in ${ENV_FILE:-environment})"

  if [[ "${AZURE_PG_RESET_SCHEMA:-}" == "true" ]]; then
    echo "==> AZURE_PG_RESET_SCHEMA=true — dropping public schema"
    psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO PUBLIC;
SQL
  fi

  gunzip -c "${dump_file}" | psql "${DATABASE_URL}" -v ON_ERROR_STOP=1
  echo "Restore complete. Restart the Container App if it was running during restore."
}

FROM_BLOB=false
DUMP_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-blob)
      FROM_BLOB=true
      shift
      ;;
    *)
      DUMP_FILE="$1"
      shift
      ;;
  esac
done

if [[ "${FROM_BLOB}" == "true" ]]; then
  DUMP_FILE="${DUMP_FILE:-${ROOT}/deploy/azure/backups/restore-from-blob.sql.gz}"
  download_from_blob "${DUMP_FILE}"
fi

: "${DUMP_FILE:?Usage: $0 [--from-blob] <file.sql.gz>}"
restore_dump "${DUMP_FILE}"

#!/usr/bin/env bash
# Dump Postgres from the current VM Docker stack and restore into Azure Flexible Server.
#
# Run dump ON THE VM (or from a machine that can reach the VM DB).
# Run restore from a machine that can reach Azure Postgres (your laptop with firewall open,
# or Azure Cloud Shell after allowing its IP).
#
# Usage — dump (on VM):
#   export COMPOSE_FILE=/opt/dscapi/docker-compose.host-nginx.yml
#   ./deploy/azure/04-db-dump-restore.sh dump /tmp/dscapi-dump.sql.gz
#
# Usage — restore (to Azure):
#   export AZURE_PG_HOST=igesign-pg.postgres.database.azure.com
#   export AZURE_PG_USER=dscapi
#   export AZURE_PG_PASSWORD='...'
#   export AZURE_PG_DB=dscapi
#   ./deploy/azure/04-db-dump-restore.sh restore /tmp/dscapi-dump.sql.gz

set -euo pipefail

ACTION="${1:?Usage: $0 dump|restore <file.sql.gz>}"
DUMP_FILE="${2:?Provide dump path, e.g. /tmp/dscapi-dump.sql.gz}"

dump_from_vm() {
  COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.host-nginx.yml}"
  echo "==> Dumping from Docker Compose Postgres (compose: ${COMPOSE_FILE})"
  # Runs pg_dump inside the db container as user dscapi
  docker compose -f "${COMPOSE_FILE}" exec -T db \
    pg_dump -U dscapi -d dscapi --no-owner --no-acl \
    | gzip > "${DUMP_FILE}"
  ls -lh "${DUMP_FILE}"
  echo "Copy this file to a machine that can reach Azure Postgres, then run restore."
}

restore_to_azure() {
  : "${AZURE_PG_HOST:?Set AZURE_PG_HOST}"
  : "${AZURE_PG_USER:?Set AZURE_PG_USER}"
  : "${AZURE_PG_PASSWORD:?Set AZURE_PG_PASSWORD}"
  : "${AZURE_PG_DB:?Set AZURE_PG_DB}"

  if [[ ! -f "${DUMP_FILE}" ]]; then
    echo "Missing dump file ${DUMP_FILE}" >&2
    exit 1
  fi

  export PGPASSWORD="${AZURE_PG_PASSWORD}"
  echo "==> Restoring ${DUMP_FILE} → ${AZURE_PG_HOST}/${AZURE_PG_DB}"
  echo "    (Target DB should exist; prefer empty or freshly created database.)"

  # Drop/recreate public schema objects safely for cutover into an empty DB:
  # If migrate already ran on Azure, either restore into a fresh DB or drop schema first.
  if [[ "${AZURE_PG_RESET_SCHEMA:-}" == "true" ]]; then
    echo "==> Resetting public schema (AZURE_PG_RESET_SCHEMA=true)"
    psql "host=${AZURE_PG_HOST} port=5432 dbname=${AZURE_PG_DB} user=${AZURE_PG_USER} sslmode=require" \
      -v ON_ERROR_STOP=1 \
      -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO ${AZURE_PG_USER}; GRANT ALL ON SCHEMA public TO public;"
  fi

  gunzip -c "${DUMP_FILE}" | psql \
    "host=${AZURE_PG_HOST} port=5432 dbname=${AZURE_PG_DB} user=${AZURE_PG_USER} sslmode=require" \
    -v ON_ERROR_STOP=1

  echo "Restore complete."
}

case "${ACTION}" in
  dump) dump_from_vm ;;
  restore) restore_to_azure ;;
  *)
    echo "Unknown action: ${ACTION}" >&2
    exit 1
    ;;
esac

#!/usr/bin/env bash
# Create Azure foundation for IG E-Sign:
#   Resource group, ACR, Log Analytics, Container Apps env, PostgreSQL Flexible Server
#
# Prerequisites: az login, Contributor on the subscription
#
# Usage:
#   export AZ_LOCATION=centralindia          # or eastus, etc.
#   export AZ_RG=rg-ig-esign
#   export AZ_PREFIX=igesign                  # short unique prefix for names
#   export PG_ADMIN_PASSWORD='StrongPassword!'
#   ./deploy/azure/01-create-resources.sh

set -euo pipefail

: "${AZ_LOCATION:?Set AZ_LOCATION (e.g. centralindia)}"
: "${AZ_RG:?Set AZ_RG (e.g. rg-ig-esign)}"
: "${AZ_PREFIX:?Set AZ_PREFIX (e.g. igesign)}"
: "${PG_ADMIN_PASSWORD:?Set PG_ADMIN_PASSWORD}"

ACR_NAME="${ACR_NAME:-${AZ_PREFIX}acr}"
ACA_ENV="${ACA_ENV:-${AZ_PREFIX}-env}"
ACA_APP="${ACA_APP:-${AZ_PREFIX}-web}"
PG_SERVER="${PG_SERVER:-${AZ_PREFIX}-pg}"
PG_DB="${PG_DB:-dscapi}"
PG_USER="${PG_USER:-dscapi}"
LAW_NAME="${LAW_NAME:-${AZ_PREFIX}-logs}"

echo "==> Resource group ${AZ_RG} (${AZ_LOCATION})"
az group create --name "${AZ_RG}" --location "${AZ_LOCATION}" --output none

echo "==> Log Analytics ${LAW_NAME}"
az monitor log-analytics workspace create \
  --resource-group "${AZ_RG}" \
  --workspace-name "${LAW_NAME}" \
  --location "${AZ_LOCATION}" \
  --output none

LAW_ID="$(az monitor log-analytics workspace show \
  --resource-group "${AZ_RG}" \
  --workspace-name "${LAW_NAME}" \
  --query customerId -o tsv)"
LAW_KEY="$(az monitor log-analytics workspace get-shared-keys \
  --resource-group "${AZ_RG}" \
  --workspace-name "${LAW_NAME}" \
  --query primarySharedKey -o tsv)"

echo "==> Azure Container Registry ${ACR_NAME}"
# ACR names must be alphanumeric only
az acr create \
  --resource-group "${AZ_RG}" \
  --name "${ACR_NAME}" \
  --sku Basic \
  --admin-enabled true \
  --output none

echo "==> Container Apps environment ${ACA_ENV}"
az containerapp env create \
  --name "${ACA_ENV}" \
  --resource-group "${AZ_RG}" \
  --location "${AZ_LOCATION}" \
  --logs-workspace-id "${LAW_ID}" \
  --logs-workspace-key "${LAW_KEY}" \
  --output none

echo "==> PostgreSQL Flexible Server ${PG_SERVER}"
# Burstable B1ms is enough for ~1000 req/day; enable backups in portal if needed.
az postgres flexible-server create \
  --resource-group "${AZ_RG}" \
  --name "${PG_SERVER}" \
  --location "${AZ_LOCATION}" \
  --admin-user "${PG_USER}" \
  --admin-password "${PG_ADMIN_PASSWORD}" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --public-access 0.0.0.0-255.255.255.255 \
  --yes \
  --output none

echo "==> Database ${PG_DB}"
az postgres flexible-server db create \
  --resource-group "${AZ_RG}" \
  --server-name "${PG_SERVER}" \
  --name "${PG_DB}" \
  --output none

# Prefer requiring SSL (default on Flexible Server)
az postgres flexible-server parameter set \
  --resource-group "${AZ_RG}" \
  --server-name "${PG_SERVER}" \
  --name require_secure_transport \
  --value on \
  --output none || true

PG_FQDN="$(az postgres flexible-server show \
  --resource-group "${AZ_RG}" \
  --name "${PG_SERVER}" \
  --query fullyQualifiedDomainName -o tsv)"

ACR_LOGIN="$(az acr show --name "${ACR_NAME}" --query loginServer -o tsv)"

cat <<EOF

Resources created.

  Resource group:     ${AZ_RG}
  ACR login server:   ${ACR_LOGIN}
  Container Apps env: ${ACA_ENV}
  Postgres FQDN:      ${PG_FQDN}
  Database:           ${PG_DB}
  DB user:            ${PG_USER}

DATABASE_URL (URL-encode password if it has special chars):
  postgres://${PG_USER}:${PG_ADMIN_PASSWORD}@${PG_FQDN}:5432/${PG_DB}?sslmode=require

Next:
  1. ./deploy/azure/02-build-push.sh
  2. Dump/restore DB (see README.md)
  3. ./deploy/azure/03-deploy-app.sh
  4. Bind custom domain + cut over DNS

Security note:
  Postgres was created with a wide public firewall for first cutover.
  After Container Apps works, tighten firewall or move to VNet integration.
EOF

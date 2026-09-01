#!/usr/bin/env bash
# Create or update the IG E-Sign Container App.
#
# Prerequisites:
#   - Resources from 01-create-resources.sh
#   - Image pushed via 02-build-push.sh
#   - Env file based on deploy/azure/env.azure.example (real secrets)
#
# Usage:
#   export AZ_RG=rg-ig-esign
#   export AZ_PREFIX=igesign
#   export IMAGE_TAG=igesignacr.azurecr.io/dscapi:YYYYMMDDHHMM
#   export ENV_FILE=deploy/azure/.env.azure   # local, gitignored secrets
#   ./deploy/azure/03-deploy-app.sh

set -euo pipefail

: "${AZ_RG:?Set AZ_RG}"
: "${AZ_PREFIX:?Set AZ_PREFIX}"
: "${IMAGE_TAG:?Set IMAGE_TAG}"
: "${ENV_FILE:?Set ENV_FILE path to filled env.azure file}"

ACA_ENV="${ACA_ENV:-${AZ_PREFIX}-env}"
ACA_APP="${ACA_APP:-${AZ_PREFIX}-web}"
ACR_NAME="${ACR_NAME:-${AZ_PREFIX}acr}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}" >&2
  exit 1
fi

# Load KEY=VALUE lines (skip comments/blank). Avoid `source` — unquoted `?` / special
# chars in DATABASE_URL and similar values are unreliable with process substitution.
while IFS= read -r line || [[ -n "${line}" ]]; do
  line="${line%$'\r'}"
  [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
  [[ "${line}" != *=* ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  key="${key#"${key%%[![:space:]]*}"}"
  key="${key%"${key##*[![:space:]]}"}"
  [[ -z "${key}" ]] && continue
  printf -v "${key}" '%s' "${val}"
  export "${key}"
done < "${ENV_FILE}"

: "${DATABASE_URL:?DATABASE_URL required in ${ENV_FILE}}"
: "${SECRET_KEY:?SECRET_KEY required}"
: "${ENCRYPTION_KEY:?ENCRYPTION_KEY required}"
: "${ALLOWED_HOSTS:?ALLOWED_HOSTS required}"
: "${CSRF_TRUSTED_ORIGINS:?CSRF_TRUSTED_ORIGINS required}"
: "${SITE_URL:?SITE_URL required}"

ACR_LOGIN="$(az acr show --name "${ACR_NAME}" --resource-group "${AZ_RG}" --query loginServer -o tsv)"
ACR_USER="$(az acr credential show --name "${ACR_NAME}" --query username -o tsv)"
ACR_PASS="$(az acr credential show --name "${ACR_NAME}" --query passwords[0].value -o tsv)"

# Env vars in .env.azure that are stored as Container App secrets (env references secretref:…)
secret_ref_name() {
  case "$1" in
    SECRET_KEY) echo secret-key ;;
    ENCRYPTION_KEY) echo encryption-key ;;
    DATABASE_URL) echo database-url ;;
    EMAIL_HOST_PASSWORD) echo email-host-password ;;
    GST_MYGSTCAFE_API_SECRET) echo gst-api-secret ;;
    ADMIN_PASSWORD) echo admin-password ;;
    *) echo "" ;;
  esac
}

# Not passed to the running app (local deploy / restore helpers only)
should_skip_var() {
  case "$1" in
    POSTGRES_PASSWORD) return 0 ;;
    *) return 1 ;;
  esac
}

SECRET_ARGS=()
ENV_ARGS=()
SEEN_ENV_KEYS=""

key_already_seen() {
  case " ${SEEN_ENV_KEYS} " in
    *" $1 "*) return 0 ;;
    *) return 1 ;;
  esac
}

mark_key_seen() {
  SEEN_ENV_KEYS+=" $1"
}

register_secret() {
  local ref="$1"
  local val="$2"
  local i existing_ref
  for i in "${!SECRET_ARGS[@]}"; do
    existing_ref="${SECRET_ARGS[$i]%%=*}"
    if [[ "${existing_ref}" == "${ref}" ]]; then
      SECRET_ARGS[$i]="${ref}=${val}"
      return
    fi
  done
  SECRET_ARGS+=("${ref}=${val}")
}

append_env_from_file() {
  local key val ref i existing_key
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
    [[ "${line}" != *=* ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ -z "${key}" ]] && continue
    should_skip_var "${key}" && continue

    if key_already_seen "${key}"; then
      echo "Warning: duplicate ${key} in ${ENV_FILE}; using last value" >&2
      for i in "${!ENV_ARGS[@]}"; do
        existing_key="${ENV_ARGS[$i]%%=*}"
        if [[ "${existing_key}" == "${key}" ]]; then
          ref="$(secret_ref_name "${key}")"
          if [[ -n "${ref}" ]]; then
            register_secret "${ref}" "${val}"
            ENV_ARGS[$i]="${key}=secretref:${ref}"
          else
            ENV_ARGS[$i]="${key}=${val}"
          fi
          continue 2
        fi
      done
    fi

    mark_key_seen "${key}"
    ref="$(secret_ref_name "${key}")"
    if [[ -n "${ref}" ]]; then
      register_secret "${ref}" "${val}"
      ENV_ARGS+=("${key}=secretref:${ref}")
    else
      ENV_ARGS+=("${key}=${val}")
    fi
  done < "${ENV_FILE}"
}

append_env_from_file

if [[ ${#SECRET_ARGS[@]} -eq 0 ]]; then
  echo "No secrets registered from ${ENV_FILE}" >&2
  exit 1
fi

echo "==> Deploying ${#ENV_ARGS[@]} env vars from ${ENV_FILE} (${#SECRET_ARGS[@]} secrets)"

join_by() {
  local IFS="$1"
  shift
  echo "$*"
}

SECRET_CSV="$(join_by ' ' "${SECRET_ARGS[@]}")"
# az wants space-separated secretname=value
ENV_CSV=("${ENV_ARGS[@]}")

exists="$(az containerapp show --name "${ACA_APP}" --resource-group "${AZ_RG}" --query name -o tsv 2>/dev/null || true)"

if [[ -z "${exists}" ]]; then
  echo "==> Creating Container App ${ACA_APP}"
  az containerapp create \
    --name "${ACA_APP}" \
    --resource-group "${AZ_RG}" \
    --environment "${ACA_ENV}" \
    --image "${IMAGE_TAG}" \
    --registry-server "${ACR_LOGIN}" \
    --registry-username "${ACR_USER}" \
    --registry-password "${ACR_PASS}" \
    --target-port 8000 \
    --ingress external \
    --min-replicas 1 \
    --max-replicas 1 \
    --cpu 0.5 \
    --memory 1.0Gi \
    --secrets ${SECRET_CSV} \
    --env-vars "${ENV_CSV[@]}" \
    --output none
else
  echo "==> Updating Container App ${ACA_APP}"
  az containerapp secret set \
    --name "${ACA_APP}" \
    --resource-group "${AZ_RG}" \
    --secrets ${SECRET_CSV} \
    --output none

  az containerapp update \
    --name "${ACA_APP}" \
    --resource-group "${AZ_RG}" \
    --image "${IMAGE_TAG}" \
    --min-replicas 1 \
    --max-replicas 1 \
    --cpu 0.5 \
    --memory 1.0Gi \
    --set-env-vars "${ENV_CSV[@]}" \
    --output none

  REV="$(az containerapp revision list \
    --name "${ACA_APP}" \
    --resource-group "${AZ_RG}" \
    --query "[?properties.active].name | [0]" -o tsv)"
  if [[ -n "${REV}" ]]; then
    echo "==> Restarting revision ${REV} (applies secret changes)"
    az containerapp revision restart \
      --name "${ACA_APP}" \
      --resource-group "${AZ_RG}" \
      --revision "${REV}" \
      --output none
  fi
fi

FQDN="$(az containerapp show \
  --name "${ACA_APP}" \
  --resource-group "${AZ_RG}" \
  --query properties.configuration.ingress.fqdn -o tsv)"

echo ""
echo "Container App ready."
echo "  Default URL: https://${FQDN}"
echo ""
echo "Before custom-domain cutover, add this host to ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS,"
echo "then re-run this script, e.g.:"
echo "  ALLOWED_HOSTS=sign.incitegravity.com,${FQDN}"
echo "  CSRF_TRUSTED_ORIGINS=https://sign.incitegravity.com,https://${FQDN}"
echo ""
echo "Bind custom domain next (see README.md)."

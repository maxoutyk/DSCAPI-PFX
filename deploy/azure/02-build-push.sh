#!/usr/bin/env bash
# Build linux/amd64 image and push to Azure Container Registry.
#
# Usage (from repo root):
#   export AZ_RG=rg-ig-esign
#   export ACR_NAME=igesignacr
#   export IMAGE_TAG=igesignacr.azurecr.io/dscapi:$(date +%Y%m%d%H%M)
#   ./deploy/azure/02-build-push.sh
#
# Or let the script derive IMAGE_TAG from ACR.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${ROOT}"

: "${AZ_RG:?Set AZ_RG}"
: "${ACR_NAME:?Set ACR_NAME}"

ACR_LOGIN="$(az acr show --name "${ACR_NAME}" --resource-group "${AZ_RG}" --query loginServer -o tsv)"
IMAGE_TAG="${IMAGE_TAG:-${ACR_LOGIN}/dscapi:$(date +%Y%m%d%H%M)}"
LATEST_TAG="${ACR_LOGIN}/dscapi:latest"

echo "==> Logging into ACR ${ACR_NAME}"
az acr login --name "${ACR_NAME}"

echo "==> Ensuring buildx (linux/amd64)"
if ! docker buildx inspect azurebuilder >/dev/null 2>&1; then
  docker buildx create --name azurebuilder --driver docker-container --use
  docker buildx inspect --bootstrap
else
  docker buildx use azurebuilder
fi

echo "==> Building and pushing ${IMAGE_TAG}"
docker buildx build \
  --platform linux/amd64 \
  -t "${IMAGE_TAG}" \
  -t "${LATEST_TAG}" \
  --push \
  .

echo ""
echo "Pushed:"
echo "  ${IMAGE_TAG}"
echo "  ${LATEST_TAG}"
echo ""
echo "Export for deploy:"
echo "  export IMAGE_TAG=${IMAGE_TAG}"

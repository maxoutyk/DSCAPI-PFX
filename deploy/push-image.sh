#!/usr/bin/env bash
set -euo pipefail

# Build linux/amd64 image on Apple Silicon, save, and rsync to server.
#
# One-time Mac setup (if build fails with "exec format error"):
#   docker run --privileged --rm tonistiigi/binfmt --install all
#   docker buildx create --name amd64builder --driver docker-container --use
#   docker buildx inspect --bootstrap
#
# Usage:
#   ./deploy/push-image.sh sup_admin@103.99.38.134
#   REMOTE_DIR=/opt/dscapi ./deploy/push-image.sh user@server

REMOTE="${1:?Usage: ./deploy/push-image.sh user@server}"
REMOTE_DIR="${REMOTE_DIR:-/opt/dscapi}"
IMAGE_TAG="${IMAGE_TAG:-dscapi:latest}"
TAR_FILE="${TAR_FILE:-dscapi-image.tar.gz}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT"

echo "Building ${IMAGE_TAG} for linux/amd64..."
if docker buildx ls | grep -q amd64builder; then
  docker buildx use amd64builder
else
  docker buildx create --name amd64builder --driver docker-container --use
  docker buildx inspect --bootstrap
fi

# Export directly to tar — avoids "docker save" checksum errors on Apple Silicon.
echo "Exporting image to ${TAR_FILE}..."
docker buildx build --platform linux/amd64 -t "${IMAGE_TAG}" \
  --output type=docker,dest=- . | gzip > "${TAR_FILE}"
ls -lh "${TAR_FILE}"

echo "Uploading to ${REMOTE}:${REMOTE_DIR}..."
rsync -avz --progress "${TAR_FILE}" \
  docker-compose.host-nginx.yml \
  deploy/env.incitegravity.example \
  deploy/nginx-sign.incitegravity.com.conf \
  "${REMOTE}:${REMOTE_DIR}/"

echo ""
echo "On the server:"
echo "  cd ${REMOTE_DIR}"
echo "  gunzip -c ${TAR_FILE} | docker load"
echo "  cp deploy/env.incitegravity.example .env   # edit secrets first if new"
echo "  docker compose -f docker-compose.host-nginx.yml up -d"
echo "  docker compose -f docker-compose.host-nginx.yml logs -f web"

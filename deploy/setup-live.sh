#!/usr/bin/env bash
set -euo pipefail

# Run on a fresh Ubuntu 22.04/24.04 VPS (as a sudo-capable user).
# Usage: curl -fsSL <raw-url>/deploy/setup-live.sh | bash
#    or: bash deploy/setup-live.sh

REPO_URL="${REPO_URL:-https://github.com/maxoutyk/DSCAPI-PFX.git}"
APP_DIR="${APP_DIR:-/opt/dscapi}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker..."
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl git
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "${USER}" || true
  echo "Docker installed. You may need to log out and back in for group changes."
fi

if [ ! -d "$APP_DIR/.git" ]; then
  echo "Cloning repository to ${APP_DIR}..."
  sudo mkdir -p "$(dirname "$APP_DIR")"
  sudo git clone "$REPO_URL" "$APP_DIR"
  sudo chown -R "${USER}:${USER}" "$APP_DIR"
else
  echo "Updating repository in ${APP_DIR}..."
  git -C "$APP_DIR" pull --ff-only
fi

cd "$APP_DIR"

if [ ! -f .env ]; then
  cp deploy/env.production.example .env
  SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
  ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || openssl rand -base64 32)"
  POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" .env
  sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${ENCRYPTION_KEY}|" .env
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASSWORD}|" .env
  echo ""
  echo "Created .env with generated secrets."
  echo "Edit ${APP_DIR}/.env before continuing:"
  echo "  - DOMAIN, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, SITE_URL"
  echo "  - ADMIN_EMAIL, ADMIN_PASSWORD"
  echo "  - EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL"
  echo ""
  echo "Then run: cd ${APP_DIR} && docker compose -f docker-compose.prod.yml up -d --build"
  exit 0
fi

echo "Building and starting production stack..."
docker compose -f docker-compose.prod.yml up -d --build

echo ""
echo "Deployment started."
echo "  App URL: https://${DOMAIN:-$(grep '^DOMAIN=' .env | cut -d= -f2)}"
echo "  Admin:   https://${DOMAIN:-your-domain}/admin/"
echo ""
echo "Useful commands:"
echo "  docker compose -f docker-compose.prod.yml logs -f web"
echo "  docker compose -f docker-compose.prod.yml exec web python manage.py send_test_email you@example.com"

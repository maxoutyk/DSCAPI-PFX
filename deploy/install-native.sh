#!/usr/bin/env bash
set -euo pipefail

# Native install alongside an existing nginx + PM2 Next.js app.
# Run with sudo for user creation, then finishes as the dscapi user.
#
# Usage:
#   sudo bash deploy/install-native.sh
#   sudo -u dscapi bash deploy/install-native.sh --app-only   # skip user creation

APP_USER="${APP_USER:-dscapi}"
APP_DIR="${APP_DIR:-/opt/dscapi}"
REPO_URL="${REPO_URL:-https://github.com/maxoutyk/DSCAPI-PFX.git}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

run_as_app_user() {
  if [ "$(id -un)" = "$APP_USER" ]; then
    "$@"
  else
    sudo -u "$APP_USER" -H "$@"
  fi
}

create_user() {
  if id "$APP_USER" &>/dev/null; then
    echo "User ${APP_USER} already exists."
    return
  fi
  useradd --system --create-home --home-dir "/home/${APP_USER}" --shell /bin/bash "$APP_USER"
  echo "Created user ${APP_USER}."
}

install_app() {
    if [ ! -d "$APP_DIR/.git" ]; then
    run_as_app_user git clone "$REPO_URL" "$APP_DIR"
  else
    run_as_app_user git -C "$APP_DIR" pull --ff-only
  fi

  cd "$APP_DIR"

  if [ ! -d venv ]; then
    run_as_app_user "$PYTHON_BIN" -m venv venv
  fi

  run_as_app_user ./venv/bin/pip install --upgrade pip
  run_as_app_user ./venv/bin/pip install -r requirements.txt
  run_as_app_user ./venv/bin/pip install endesive==2.17.2 --no-deps

  if [ ! -f .env ]; then
    cp deploy/env.production.example .env
    SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
    ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || openssl rand -base64 32)"
    POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" .env
    sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${ENCRYPTION_KEY}|" .env
    sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASSWORD}|" .env
    echo "Created ${APP_DIR}/.env — edit DOMAIN, SITE_URL, SMTP, and admin credentials."
  fi

  set -a
  # shellcheck disable=SC1091
  source .env
  set +a

  run_as_app_user env DJANGO_SETTINGS_MODULE=DSCApi.settings ./venv/bin/python manage.py migrate --noinput
  run_as_app_user env DJANGO_SETTINGS_MODULE=DSCApi.settings ./venv/bin/python manage.py collectstatic --noinput
  run_as_app_user env DJANGO_SETTINGS_MODULE=DSCApi.settings ./venv/bin/python manage.py bootstrap_admin
}

if [ "${1:-}" = '--app-only' ]; then
  install_app
  exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo for first-time install (creates ${APP_USER} user)."
  exit 1
fi

create_user
mkdir -p "$APP_DIR"
chown -R "${APP_USER}:${APP_USER}" "$APP_DIR"
sudo -u "$APP_USER" -H bash "$(dirname "$0")/install-native.sh" --app-only

echo ""
echo "App installed in ${APP_DIR} as user ${APP_USER}."
echo "Next steps:"
echo "  1. Edit ${APP_DIR}/.env (DOMAIN, SITE_URL, ALLOWED_HOSTS, SMTP, admin)"
echo "  2. sudo cp ${APP_DIR}/deploy/dscapi.service /etc/systemd/system/"
echo "  3. sudo systemctl daemon-reload && sudo systemctl enable --now dscapi"
echo "  4. sudo cp ${APP_DIR}/deploy/nginx-sign.incitegravity.com.conf /etc/nginx/sites-available/dscapi"
echo "  5. sudo ln -sf /etc/nginx/sites-available/dscapi /etc/nginx/sites-enabled/dscapi"
echo "  6. sudo nginx -t && sudo systemctl reload nginx"
echo "  7. sudo certbot --nginx -d sign.incitegravity.com"

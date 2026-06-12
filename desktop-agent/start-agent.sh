#!/usr/bin/env bash
# IG E-Sign USB Agent — macOS / Linux launcher
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install Python 3.10+ and retry."
  exit 1
fi

API_BASE=""
if [[ -f portal.url ]]; then
  API_BASE="$(grep -E '^api_base=' portal.url | cut -d= -f2- | tr -d '\r')"
fi
if [[ -z "$API_BASE" ]]; then
  read -r -p "Portal URL (e.g. https://sign.incitegravity.com): " API_BASE
fi

if [[ ! -f .paired ]]; then
  read -r -p "Enter pairing code from USB Agent page: " CODE
  python3 agent.py pair --api-base "$API_BASE" --code "$CODE"
  touch .paired
fi

echo "Starting agent on http://127.0.0.1:9765"
python3 agent.py run --port 9765

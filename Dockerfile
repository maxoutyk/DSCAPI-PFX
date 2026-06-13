FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=DSCApi.settings

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libmupdf-dev libssl3 openssl libssl-dev libffi-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Server image: skip desktop/USB-token-only deps (PyKCS11, pystray, waitress).
RUN pip install --no-cache-dir $(grep -vE '^(endesive|PyKCS11|pystray|waitress)' requirements.txt) \
    && pip install --no-cache-dir endesive==2.17.2 --no-deps \
    && pip install --no-cache-dir requests==2.34.2 paramiko==3.4.0

COPY docker/patch_oscrypto.py /tmp/patch_oscrypto.py
RUN python /tmp/patch_oscrypto.py \
    && python -c "from endesive import pdf; print('endesive import ok')"

COPY . .
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/bin/sh", "docker/entrypoint.sh"]

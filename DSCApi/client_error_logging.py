"""Log client-error HTTP responses with a redacted reason for troubleshooting."""

from __future__ import annotations

import json
import logging

from accounts.log_filters import redact_sensitive_text
from signPdf.audit import get_client_ip

logger = logging.getLogger('http.client_error')


def summarize_response_body(response, *, max_len: int = 500) -> str:
    data = getattr(response, 'data', None)
    if data is not None:
        try:
            text = json.dumps(data, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(data)
    else:
        content = getattr(response, 'content', b'') or b''
        if not content:
            return ''
        text = content.decode('utf-8', errors='replace')
        head = text.lstrip()[:200].lower()
        if head.startswith('<!doctype html') or head.startswith('<html'):
            return '<html response>'

    text = redact_sensitive_text(text.strip())
    if len(text) > max_len:
        return f'{text[:max_len]}...'
    return text


def request_actor(request) -> str:
    user = getattr(request, 'user', None)
    if user is None:
        return 'anonymous'
    tenant = getattr(user, 'tenant', None)
    if tenant is not None:
        slug = getattr(tenant, 'slug', None) or getattr(tenant, 'name', None)
        if slug:
            return f'tenant:{slug}'
    if getattr(user, 'is_authenticated', False):
        username = getattr(user, 'username', None)
        if username:
            return str(username)
    return 'anonymous'


class ClientErrorLoggingMiddleware:
    """Log configured 4xx responses with path, actor, IP, and redacted error detail."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        from django.conf import settings

        log_status_codes = getattr(settings, 'LOG_CLIENT_ERROR_STATUS_CODES', (400, 403, 404))
        if response.status_code not in log_status_codes:
            return response
        if request.path.startswith('/static/'):
            return response

        detail = summarize_response_body(response)
        logger.warning(
            'HTTP %s %s %s actor=%s ip=%s detail=%s',
            response.status_code,
            request.method,
            request.get_full_path(),
            request_actor(request),
            get_client_ip(request) or '-',
            detail or '-',
        )
        return response

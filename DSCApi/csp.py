"""Content-Security-Policy helpers (nonce-based scripts, no unsafe-inline for JS)."""

from __future__ import annotations

import secrets

from django.conf import settings


def generate_csp_nonce() -> str:
    return secrets.token_urlsafe(16)


def csp_header_value(nonce: str) -> str:
    """Build a strict CSP. Inline style attributes still use style-src 'unsafe-inline'."""
    script_src = [
        "'self'",
        f"'nonce-{nonce}'",
        'https://cdnjs.cloudflare.com',
        'https://cdn.jsdelivr.net',
        'https://www.googletagmanager.com',
    ]
    style_src = [
        "'self'",
        "'unsafe-inline'",
        'https://fonts.googleapis.com',
    ]
    img_src = [
        "'self'",
        'data:',
        'https://www.googletagmanager.com',
        'https://www.google-analytics.com',
    ]
    connect_src = [
        "'self'",
        'https://www.google-analytics.com',
        'https://www.googletagmanager.com',
        'https://cdnjs.cloudflare.com',
    ]
    extra_script = getattr(settings, 'CSP_EXTRA_SCRIPT_SRC', '')
    if extra_script:
        script_src.extend(item.strip() for item in extra_script.split() if item.strip())

    directives = [
        "default-src 'self'",
        f"script-src {' '.join(script_src)}",
        f"style-src {' '.join(style_src)}",
        f"img-src {' '.join(img_src)}",
        "font-src 'self' https://fonts.gstatic.com data:",
        f"connect-src {' '.join(connect_src)}",
        "worker-src 'self' blob: https://cdnjs.cloudflare.com",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
        "upgrade-insecure-requests",
    ]
    return '; '.join(directives)


def should_apply_csp(path: str) -> bool:
    """Django admin and static assets keep their own inline script requirements."""
    if path.startswith('/admin/'):
        return False
    if path.startswith('/static/'):
        return False
    return True

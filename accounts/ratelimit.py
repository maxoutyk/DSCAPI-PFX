from django.conf import settings

from django.core.cache import cache

from signPdf.audit import get_client_ip

from .safe_cache import safe_cache_get, safe_cache_set

SIGNING_RATE_LIMIT_SCOPES = frozenset({
    'portal_sign',
    'portal_sign_preview',
    'public_sign',
    'public_sign_preview',
})


def client_ip(request) -> str:
    return get_client_ip(request) or 'unknown'


def is_rate_limited(request, scope: str, *, limit: int | None = None, period: int | None = None) -> bool:
    max_requests = limit if limit is not None else settings.RATELIMIT_DEFAULT_LIMIT
    window = period if period is not None else settings.RATELIMIT_DEFAULT_PERIOD
    key = f'ratelimit:{scope}:{client_ip(request)}'
    fail_closed = scope in SIGNING_RATE_LIMIT_SCOPES
    try:
        count = cache.get(key, 0)
    except Exception:
        import logging

        logging.getLogger(__name__).exception('Rate limit cache read failed for %s', scope)
        return fail_closed
    return count >= max_requests


def record_rate_limit_hit(request, scope: str, *, limit: int | None = None, period: int | None = None):
    max_requests = limit if limit is not None else settings.RATELIMIT_DEFAULT_LIMIT
    window = period if period is not None else settings.RATELIMIT_DEFAULT_PERIOD
    key = f'ratelimit:{scope}:{client_ip(request)}'
    count = safe_cache_get(key, 0)
    safe_cache_set(key, count + 1, window)


RATE_LIMIT_MESSAGE = 'Too many attempts. Please wait a few minutes and try again.'

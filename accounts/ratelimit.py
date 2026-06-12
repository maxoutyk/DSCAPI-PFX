from django.conf import settings
from django.core.cache import cache

from signPdf.audit import get_client_ip


def client_ip(request) -> str:
    return get_client_ip(request) or 'unknown'


def is_rate_limited(request, scope: str, *, limit: int | None = None, period: int | None = None) -> bool:
    max_requests = limit if limit is not None else settings.RATELIMIT_DEFAULT_LIMIT
    window = period if period is not None else settings.RATELIMIT_DEFAULT_PERIOD
    key = f'ratelimit:{scope}:{client_ip(request)}'
    return cache.get(key, 0) >= max_requests


def record_rate_limit_hit(request, scope: str, *, limit: int | None = None, period: int | None = None):
    max_requests = limit if limit is not None else settings.RATELIMIT_DEFAULT_LIMIT
    window = period if period is not None else settings.RATELIMIT_DEFAULT_PERIOD
    key = f'ratelimit:{scope}:{client_ip(request)}'
    count = cache.get(key, 0)
    cache.set(key, count + 1, window)


RATE_LIMIT_MESSAGE = 'Too many attempts. Please wait a few minutes and try again.'

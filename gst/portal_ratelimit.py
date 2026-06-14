"""Per-tenant rate limits for the GST portal try endpoint (mirrors API throttles)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

GST_PORTAL_RATE_LIMIT_MESSAGE = 'Too many GST lookups. Please wait a moment and try again.'


def _parse_rate(scope: str) -> tuple[int, int]:
    raw = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].get(scope, '120/hour')
    count, period_name = raw.split('/')
    periods = {'sec': 1, 'min': 60, 'hour': 3600, 'day': 86400}
    return int(count), periods[period_name]


def _is_limited(tenant_pk: int, scope: str, key_suffix: str) -> bool:
    limit, window = _parse_rate(scope)
    key = f'gst-portal-{key_suffix}-tenant-{tenant_pk}'
    try:
        count = cache.get(key, 0)
        if count >= limit:
            return True
        cache.set(key, count + 1, window)
        return False
    except Exception:
        logger.exception('GST portal rate limit cache failure for tenant %s', tenant_pk)
        return True


def is_gst_portal_rate_limited(tenant_pk: int) -> bool:
    if _is_limited(tenant_pk, 'gst_lookup_burst', 'burst'):
        return True
    return _is_limited(tenant_pk, 'gst_lookup', 'hourly')

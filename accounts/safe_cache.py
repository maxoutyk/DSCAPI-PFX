import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


def safe_cache_get(key, default=None):
    try:
        return cache.get(key, default)
    except Exception:
        logger.exception('Cache get failed for key %s', key)
        return default


def safe_cache_set(key, value, timeout):
    try:
        cache.set(key, value, timeout)
    except Exception:
        logger.exception('Cache set failed for key %s', key)

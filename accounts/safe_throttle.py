import logging

from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger(__name__)


class SafeSimpleRateThrottle(SimpleRateThrottle):
    """Rate limit via cache; allow the request if the cache backend is unavailable."""

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            logger.exception('Rate throttle cache failure for scope %s', self.scope)
            return True


class FailClosedSimpleRateThrottle(SimpleRateThrottle):
    """Deny requests when the cache backend is unavailable (signing endpoints)."""

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            logger.exception('Rate throttle cache failure for scope %s — denying request', self.scope)
            return False

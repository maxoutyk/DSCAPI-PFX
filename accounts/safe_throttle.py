from rest_framework.throttling import SimpleRateThrottle


class SafeSimpleRateThrottle(SimpleRateThrottle):
    """Rate limit via cache; allow the request if the cache backend is unavailable."""

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            return True

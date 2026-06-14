from accounts.safe_throttle import FailClosedSimpleRateThrottle


class GstLookupUserThrottle(FailClosedSimpleRateThrottle):
    scope = 'gst_lookup'

    def get_cache_key(self, request, view):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return None
        tenant = getattr(request.user, 'tenant', None)
        if not tenant:
            return None
        return f'gst-lookup-tenant-{tenant.pk}'


class GstLookupBurstThrottle(FailClosedSimpleRateThrottle):
    scope = 'gst_lookup_burst'

    def get_cache_key(self, request, view):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return None
        tenant = getattr(request.user, 'tenant', None)
        if not tenant:
            return None
        return f'gst-lookup-burst-tenant-{tenant.pk}'

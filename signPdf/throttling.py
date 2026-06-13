from accounts.safe_throttle import SafeSimpleRateThrottle


class SignPdfUserThrottle(SafeSimpleRateThrottle):
    """Per API key or client IP — limits expensive PDF signing."""

    scope = 'sign_pdf'

    def get_cache_key(self, request, view):
        api_key = getattr(request.user, 'api_key', None)
        if api_key:
            return f'throttle_sign_key_{api_key.prefix}'
        return f'throttle_sign_ip_{self.get_ident(request)}'


class SignPdfBurstThrottle(SafeSimpleRateThrottle):
    scope = 'sign_pdf_burst'

    def get_cache_key(self, request, view):
        api_key = getattr(request.user, 'api_key', None)
        if api_key:
            return f'throttle_sign_burst_{api_key.prefix}'
        return f'throttle_sign_burst_ip_{self.get_ident(request)}'

from DSCApi.csp import csp_header_value, generate_csp_nonce, should_apply_csp


class ContentSecurityPolicyMiddleware:
    """Attach a per-request CSP nonce and strict Content-Security-Policy header."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = generate_csp_nonce()
        response = self.get_response(request)
        if should_apply_csp(request.path):
            response.headers['Content-Security-Policy'] = csp_header_value(request.csp_nonce)
        return response

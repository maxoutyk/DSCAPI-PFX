from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .services import authenticate_api_key


class APIKeyUser:
    """Lightweight user object attached to API-key-authenticated requests."""

    is_authenticated = True
    is_active = True

    def __init__(self, api_key, tenant):
        self.api_key = api_key
        self.tenant = tenant
        self.username = f'apikey:{api_key.prefix}'


class APIKeyAuthentication(BaseAuthentication):
    keyword = 'Bearer'

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith(f'{self.keyword} '):
            return None

        raw_key = auth_header[len(self.keyword) + 1 :].strip()
        if not raw_key:
            return None

        result = authenticate_api_key(raw_key)
        if not result:
            raise AuthenticationFailed('Invalid or revoked API key.')

        api_key, tenant = result
        user = APIKeyUser(api_key, tenant)
        return (user, api_key)

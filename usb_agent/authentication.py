from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import AgentDevice
from .services import authenticate_device


class AgentDeviceUser:
    is_authenticated = True
    is_active = True

    def __init__(self, device: AgentDevice):
        self.device = device
        self.tenant = device.tenant
        self.username = f'agent:{device.prefix}'


class AgentDeviceAuthentication(BaseAuthentication):
    keyword = 'Bearer'

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith(f'{self.keyword} '):
            return None

        raw_token = auth_header[len(self.keyword) + 1 :].strip()
        device = authenticate_device(raw_token)
        if not device:
            raise AuthenticationFailed('Invalid or revoked agent device token.')
        return (AgentDeviceUser(device), device)

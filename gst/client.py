"""MyGSTCafe GST common API client (lookup services).

Partner base URL and credentials are server-only — never expose in templates,
JavaScript, API docs shown to tenants, or error responses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class MyGSTCafeConfigError(Exception):
    """Platform MyGSTCafe credentials are not configured."""


class MyGSTCafeAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True)
class MyGSTCafeCredentials:
    customer_id: str
    api_id: str
    api_secret: str
    environment: str


def get_platform_credentials() -> MyGSTCafeCredentials:
    customer_id = getattr(settings, 'GST_MYGSTCAFE_CUSTOMER_ID', '').strip()
    api_id = getattr(settings, 'GST_MYGSTCAFE_API_ID', '').strip()
    api_secret = getattr(settings, 'GST_MYGSTCAFE_API_SECRET', '').strip()
    environment = getattr(settings, 'GST_MYGSTCAFE_ENVIRONMENT', 'Sandbox').strip() or 'Sandbox'
    if not customer_id or not api_id or not api_secret:
        raise MyGSTCafeConfigError('GST partner credentials are not configured on this server.')
    if environment not in {'Sandbox', 'Production'}:
        raise MyGSTCafeConfigError('GST_MYGSTCAFE_ENVIRONMENT must be Sandbox or Production.')
    return MyGSTCafeCredentials(
        customer_id=customer_id,
        api_id=api_id,
        api_secret=api_secret,
        environment=environment,
    )


def _partner_base_url() -> str:
    return getattr(settings, 'GST_PARTNER_BASE_URL', '').strip().rstrip('/')


def _public_error_message(status_code: int) -> str:
    if status_code == 404:
        return 'GSTIN not found on the GST network.'
    if status_code == 401 or status_code == 403:
        return 'GST network authentication failed. Contact support.'
    if 400 <= status_code < 500:
        return 'GST lookup request was rejected.'
    return 'GST network service is temporarily unavailable.'


class MyGSTCafeLookupClient:
    def __init__(self, credentials: MyGSTCafeCredentials | None = None):
        self.credentials = credentials or get_platform_credentials()

    def _headers(self, *, client_ip: str | None = None) -> dict[str, str]:
        headers = {
            'CustomerId': self.credentials.customer_id,
            'APIId': self.credentials.api_id,
            'APISecret': self.credentials.api_secret,
            'environment-type': self.credentials.environment,
            'Accept': 'application/json',
        }
        if client_ip:
            headers['ip-usr'] = client_ip
        return headers

    def _request(self, path: str, *, params: dict[str, str], client_ip: str | None = None) -> Any:
        base_url = _partner_base_url()
        if not base_url:
            raise MyGSTCafeConfigError('GST partner base URL is not configured on this server.')

        query = urlencode({k: v for k, v in params.items() if v is not None and v != ''})
        url = f'{base_url}{path}'
        if query:
            url = f'{url}?{query}'
        timeout = getattr(settings, 'GST_MYGSTCAFE_TIMEOUT_SECONDS', 30)
        try:
            response = requests.get(
                url,
                headers=self._headers(client_ip=client_ip),
                timeout=timeout,
            )
        except requests.RequestException as exc:
            logger.warning('GST partner request failed: %s', exc.__class__.__name__)
            raise MyGSTCafeAPIError('Unable to reach GST network service.') from exc

        if response.status_code >= 500:
            logger.warning('GST partner upstream error status=%s', response.status_code)
            raise MyGSTCafeAPIError(
                'GST network service is temporarily unavailable.',
                status_code=response.status_code,
            )

        content_type = (response.headers.get('Content-Type') or '').lower()
        if 'application/json' in content_type:
            try:
                payload = response.json()
            except ValueError as exc:
                logger.warning('GST partner returned invalid JSON status=%s', response.status_code)
                raise MyGSTCafeAPIError(
                    'GST network returned an invalid response.',
                    status_code=response.status_code,
                ) from exc
        else:
            logger.warning(
                'GST partner returned non-JSON status=%s content_type=%s',
                response.status_code,
                content_type or 'unknown',
            )
            if response.status_code >= 400:
                raise MyGSTCafeAPIError(
                    _public_error_message(response.status_code),
                    status_code=response.status_code,
                )
            raise MyGSTCafeAPIError(
                'GST network returned an invalid response.',
                status_code=response.status_code,
            )

        if response.status_code >= 400:
            logger.warning('GST partner client error status=%s', response.status_code)
            raise MyGSTCafeAPIError(
                _public_error_message(response.status_code),
                status_code=response.status_code,
                payload=payload if isinstance(payload, dict) else None,
            )

        return payload

    def get_gstin_details(self, gstin: str) -> Any:
        return self._request(
            '/managed/commonapi/v1.1/search',
            params={'gstin': gstin},
        )

    def get_preference(self, gstin: str, fy: str) -> Any:
        return self._request(
            '/managed/commonapi/v1.0/getpreference',
            params={'gstin': gstin, 'fy': fy},
        )

    def get_return_status(self, gstin: str, fy: str, *, return_type: str = '', client_ip: str | None = None) -> Any:
        return self._request(
            '/managed/commonapi/v1.0/returns',
            params={'gstin': gstin, 'fy': fy, 'type': return_type},
            client_ip=client_ip,
        )

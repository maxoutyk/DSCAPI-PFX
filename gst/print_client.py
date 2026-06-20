"""MyGSTCafe print APIs (E-WAY bill and E-invoice IRN PDF downloads).



Partner hosts and platform credentials are server-only. NIC portal username/password

are per-tenant and stored on the company profile.

"""



from __future__ import annotations



import json

import logging

from typing import Any

from urllib.parse import urlencode



import requests

from django.conf import settings



from signPdf.validation import validate_pdf_bytes



from .client import (

    MyGSTCafeAPIError,

    MyGSTCafeConfigError,

    MyGSTCafeCredentials,

    _public_partner_status_error,

    get_platform_credentials,

)



logger = logging.getLogger(__name__)





def _eway_base_url() -> str:

    return getattr(settings, 'GST_EWAY_BASE_URL', 'https://ewayapi.mygstcafe.com').strip().rstrip('/')





def _einvoice_base_url(environment: str) -> str:

    if environment == 'Production':

        return (

            getattr(settings, 'GST_EINVOICE_BASE_URL', 'https://api.mygstcafe.com')

            .strip()

            .rstrip('/')

        )

    return (

        getattr(settings, 'GST_EINVOICE_BASE_URL_SANDBOX', 'https://testapi.mygstcafe.com')

        .strip()

        .rstrip('/')

    )





def _public_print_error_message(status_code: int) -> str:

    if status_code == 404:

        return 'Document not found on the GST network.'

    if status_code in {401, 403}:

        return 'GST network authentication failed. Check NIC portal credentials on your company profile.'

    if 400 <= status_code < 500:

        return 'Print request was rejected by the GST network.'

    return 'GST network service is temporarily unavailable.'





def _raise_for_print_partner_status(payload: Any) -> None:

    if not isinstance(payload, dict):

        return

    status_val = payload.get('status_cd', payload.get('status'))

    if status_val is None:

        return

    if str(status_val).strip() not in {'0', 'false', 'False'}:

        return



    error = payload.get('error')

    error_cd = ''

    partner_message = ''

    if isinstance(error, dict):

        error_cd = str(error.get('error_cd', '')).strip()

        partner_message = str(error.get('message', '')).strip()

    elif isinstance(error, str):

        partner_message = error.strip()

    elif isinstance(error, list) and error:

        first = error[0]

        if isinstance(first, dict):

            error_cd = str(first.get('error_cd', '')).strip()

            partner_message = str(first.get('error_message', first.get('message', ''))).strip()

        else:

            partner_message = str(first).strip()



    logger.warning(

        'GST print partner business error status=%s error_cd=%s message=%s',

        status_val,

        error_cd,

        partner_message,

    )

    raise MyGSTCafeAPIError(

        _public_partner_status_error(error_cd=error_cd, partner_message=partner_message),

        status_code=503,

        payload={'error_cd': error_cd} if error_cd else None,

    )





class MyGSTCafePrintClient:

    def __init__(self, credentials: MyGSTCafeCredentials | None = None):

        self.credentials = credentials or get_platform_credentials()



    def _headers(self, gstin: str, *, nic_username: str, nic_password: str) -> dict[str, str]:

        return {

            'username': nic_username,

            'password': nic_password,

            'gstin': gstin,

            'customerid': self.credentials.customer_id,

            'apiid': self.credentials.api_id,

            'apisecret': self.credentials.api_secret,

            'source': 'API',

            'environment-type': self.credentials.environment,

            'Accept': 'application/pdf, application/json',

        }



    def _request_pdf(

        self,

        *,

        base_url: str,

        path: str,

        params: dict[str, str],

        gstin: str,

        nic_username: str,

        nic_password: str,

    ) -> bytes:

        if not base_url:

            raise MyGSTCafeConfigError('GST print service URL is not configured on this server.')



        query = urlencode({k: v for k, v in params.items() if v is not None and v != ''})

        url = f'{base_url}{path}'

        if query:

            url = f'{url}?{query}'

        timeout = getattr(settings, 'GST_MYGSTCAFE_TIMEOUT_SECONDS', 30)

        try:

            response = requests.get(

                url,

                headers=self._headers(gstin, nic_username=nic_username, nic_password=nic_password),

                timeout=timeout,

            )

        except requests.RequestException as exc:

            logger.warning('GST print partner request failed: %s', exc.__class__.__name__)

            raise MyGSTCafeAPIError('Unable to reach GST network service.') from exc



        if response.status_code >= 500:

            logger.warning('GST print partner upstream error status=%s', response.status_code)

            raise MyGSTCafeAPIError(

                'GST network service is temporarily unavailable.',

                status_code=response.status_code,

            )



        content_type = (response.headers.get('Content-Type') or '').lower()

        body = response.content or b''

        if 'pdf' in content_type or body.startswith(b'%PDF'):

            try:

                validate_pdf_bytes(body)

            except Exception as exc:

                logger.warning('GST print partner returned invalid PDF')

                raise MyGSTCafeAPIError('GST network returned an invalid PDF.') from exc

            if response.status_code >= 400:

                raise MyGSTCafeAPIError(

                    _public_print_error_message(response.status_code),

                    status_code=response.status_code,

                )

            return body



        payload: Any = None

        if body:

            try:

                payload = response.json()

            except ValueError:

                payload = None



        if response.status_code >= 400:

            logger.warning('GST print partner client error status=%s', response.status_code)

            if isinstance(payload, dict):

                _raise_for_print_partner_status(payload)

            raise MyGSTCafeAPIError(

                _public_print_error_message(response.status_code),

                status_code=response.status_code,

                payload=payload if isinstance(payload, dict) else None,

            )



        if isinstance(payload, dict):

            _raise_for_print_partner_status(payload)

            raise MyGSTCafeAPIError(

                'GST network returned an unexpected response.',

                status_code=response.status_code,

                payload=payload,

            )



        if body:

            try:

                text = body.decode('utf-8', errors='replace')

                payload = json.loads(text)

                if isinstance(payload, dict):

                    _raise_for_print_partner_status(payload)

            except (UnicodeDecodeError, json.JSONDecodeError):

                pass



        logger.warning(

            'GST print partner returned non-PDF status=%s content_type=%s',

            response.status_code,

            content_type or 'unknown',

        )

        raise MyGSTCafeAPIError(

            'GST network returned an invalid response.',

            status_code=response.status_code,

        )



    def get_eway_detailed_print(

        self,

        ewb_number: str,

        gstin: str,

        *,

        nic_username: str,

        nic_password: str,

    ) -> bytes:

        return self._request_pdf(

            base_url=_eway_base_url(),

            path='/managed/v1.03/DetailedPrint',

            params={'ewbNumber': ewb_number},

            gstin=gstin,

            nic_username=nic_username,

            nic_password=nic_password,

        )



    def get_einvoice_pdf(

        self,

        irn: str,

        gstin: str,

        *,

        nic_username: str,

        nic_password: str,

    ) -> bytes:

        return self._request_pdf(

            base_url=_einvoice_base_url(self.credentials.environment),

            path='/einvoice/api/v1/managed/einvoicepdf',

            params={'irn': irn},

            gstin=gstin,

            nic_username=nic_username,

            nic_password=nic_password,

        )



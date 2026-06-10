import base64

from django.conf import settings
from endesive import pdf
from rest_framework import serializers, status
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import APIKeyAuthentication
from accounts.models import StoredCertificate
from accounts.services import (
    QuotaExceededError,
    TenantNotActiveError,
    ensure_tenant_can_sign,
    get_stored_certificate_bytes,
    record_signing_usage,
)

from .throttling import SignPdfBurstThrottle, SignPdfUserThrottle
from .pdf_signing import (
    SIGNATURE_ANCHOR_TEXT,
    build_signing_dict,
    find_text_in_pdf,
    get_cn_from_certificate,
    get_indian_time_str,
    load_pfx_credentials,
    read_pfx_file,
    sign_pdf_at_positions,
)


class PDFPfxSignSerializer(serializers.Serializer):
    pdf_base64 = serializers.CharField()
    password = serializers.CharField()
    pfx_base64 = serializers.CharField(required=False, allow_blank=True)
    pfx_path = serializers.CharField(required=False, allow_blank=True)
    cert_alias = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, saas_mode=False, **kwargs):
        self.saas_mode = saas_mode
        super().__init__(*args, **kwargs)

    def validate(self, data):
        pfx_b64 = (data.get('pfx_base64') or '').strip()
        pfx_path = (data.get('pfx_path') or '').strip()
        cert_alias = (data.get('cert_alias') or '').strip()

        if self.saas_mode:
            if pfx_path:
                raise serializers.ValidationError(
                    {'pfx_path': 'pfx_path is not supported with API key auth. Use pfx_base64 or cert_alias.'}
                )
            sources = [bool(pfx_b64), bool(cert_alias)]
            if sum(sources) != 1:
                raise serializers.ValidationError(
                    'Provide exactly one of pfx_base64 or cert_alias.'
                )
        else:
            if cert_alias:
                raise serializers.ValidationError(
                    {'cert_alias': 'cert_alias requires API key authentication.'}
                )
            if bool(pfx_b64) == bool(pfx_path):
                raise serializers.ValidationError(
                    'Provide exactly one of pfx_path or pfx_base64.'
                )

        data['pfx_base64'] = pfx_b64
        data['pfx_path'] = pfx_path
        data['cert_alias'] = cert_alias
        return data


class PDFPfxSignAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SignPdfBurstThrottle, SignPdfUserThrottle]

    def get_authenticators(self):
        classes = [APIKeyAuthentication]
        if settings.ALLOW_BASIC_AUTH:
            classes.append(BasicAuthentication)
        return [auth() for auth in classes]

    def _is_saas_request(self, request):
        return bool(getattr(request.user, 'tenant', None))

    def post(self, request):
        saas_mode = self._is_saas_request(request)
        serializer = PDFPfxSignSerializer(data=request.data, saas_mode=saas_mode)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        tenant = getattr(request.user, 'tenant', None)
        if saas_mode:
            try:
                ensure_tenant_can_sign(tenant)
            except TenantNotActiveError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        pdf_b64 = serializer.validated_data['pdf_base64']
        pfx_b64 = serializer.validated_data['pfx_base64']
        pfx_path = serializer.validated_data['pfx_path']
        cert_alias = serializer.validated_data['cert_alias']
        password = serializer.validated_data['password']

        try:
            pdf_data = base64.b64decode(pdf_b64)
        except Exception as exc:
            return Response(
                {'error': f'Failed to decode base64 PDF data: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if cert_alias:
                pfx_data = get_stored_certificate_bytes(tenant, cert_alias)
            elif pfx_path:
                pfx_data = read_pfx_file(pfx_path)
            else:
                pfx_data = base64.b64decode(pfx_b64)
        except StoredCertificate.DoesNotExist:  # noqa: TRY003
            return Response({'error': f'Certificate not found: {cert_alias}'}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            if cert_alias:
                return Response(
                    {'error': f'Failed to load saved certificate: {exc}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {'error': f'Failed to decode base64 PFX data: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            private_key, certificate, additional_certs = load_pfx_credentials(pfx_data, password)
        except ValueError as exc:
            if saas_mode:
                record_signing_usage(tenant, success=False)
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        text_positions = find_text_in_pdf(pdf_data, SIGNATURE_ANCHOR_TEXT)
        if not text_positions:
            if saas_mode:
                record_signing_usage(tenant, success=False)
            return Response({'error': 'No position found for signature'}, status=status.HTTP_400_BAD_REQUEST)

        indian_time_str, indian_time = get_indian_time_str()
        cn = get_cn_from_certificate(certificate)
        dct = build_signing_dict(cn, indian_time_str, indian_time)

        try:
            signed_pdf_data = sign_pdf_at_positions(
                pdf_data,
                text_positions,
                dct,
                lambda data, position_dct: pdf.cms.sign(
                    data,
                    position_dct,
                    private_key,
                    certificate,
                    additional_certs,
                    'sha256',
                ),
            )
        except Exception as exc:
            if saas_mode:
                record_signing_usage(tenant, success=False)
            return Response(
                {'error': f'Failed to sign PDF: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if saas_mode:
            try:
                record_signing_usage(tenant, success=True)
            except QuotaExceededError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        return Response(
            {
                'message': 'PDF signed successfully using PFX.',
                'signed_pdf_base64': base64.b64encode(signed_pdf_data).decode(),
            },
            status=status.HTTP_200_OK,
        )
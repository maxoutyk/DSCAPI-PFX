import base64

from django.conf import settings
from rest_framework import serializers, status
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import APIKeyAuthentication
from accounts.services import TenantNotActiveError, ensure_tenant_can_sign

from .audit import SigningAuditMeta
from .signing_service import (
    SigningFailure,
    build_audit_for_http_request,
    record_signing_failure,
    sign_pdf_for_tenant,
)
from .throttling import SignPdfBurstThrottle, SignPdfUserThrottle
from .validation import PdfValidationError, PfxValidationError, decode_pdf_base64, decode_pfx_base64


class PDFPfxSignSerializer(serializers.Serializer):
    pdf_base64 = serializers.CharField()
    password = serializers.CharField()
    pfx_base64 = serializers.CharField(required=False, allow_blank=True)
    pfx_path = serializers.CharField(required=False, allow_blank=True)
    cert_alias = serializers.CharField(required=False, allow_blank=True)
    signature_style = serializers.CharField(required=False, allow_blank=True)

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
        data['signature_style'] = (data.get('signature_style') or '').strip()
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
        api_key = getattr(request.user, 'api_key', None) if saas_mode else None
        audit = (
            build_audit_for_http_request(request, api_key=api_key)
            if saas_mode
            else None
        )

        if saas_mode:
            try:
                ensure_tenant_can_sign(tenant)
            except TenantNotActiveError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        pdf_b64 = serializer.validated_data['pdf_base64']
        pfx_b64 = serializer.validated_data['pfx_base64']
        pfx_path = serializer.validated_data['pfx_path']
        cert_alias = serializer.validated_data['cert_alias']
        signature_style = serializer.validated_data['signature_style']
        password = serializer.validated_data['password']

        try:
            pdf_data = decode_pdf_base64(pdf_b64)
        except PdfValidationError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        pfx_data = None
        if not cert_alias and not pfx_path and pfx_b64:
            try:
                pfx_data = decode_pfx_base64(pfx_b64)
            except PfxValidationError as exc:
                if saas_mode and audit:
                    audit.populate_from_pdf(pdf_data)
                    record_signing_failure(tenant, audit)
                return Response(
                    {'error': str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if saas_mode:
            try:
                result = sign_pdf_for_tenant(
                    tenant=tenant,
                    pdf_data=pdf_data,
                    password=password,
                    audit=audit,
                    cert_alias=cert_alias,
                    pfx_data=pfx_data,
                    pfx_path=pfx_path,
                    signature_style_name=signature_style,
                )
            except SigningFailure as exc:
                if exc.record_failure and audit:
                    if not audit.hash_before:
                        audit.populate_from_pdf(pdf_data)
                    record_signing_failure(tenant, audit)
                status_code = (
                    status.HTTP_429_TOO_MANY_REQUESTS
                    if 'quota' in exc.message.lower()
                    else status.HTTP_400_BAD_REQUEST
                )
                return Response({'error': exc.message}, status=status_code)

            response_body = {
                'message': 'PDF signed successfully using PFX.',
                'signed_pdf_base64': base64.b64encode(result.signed_pdf_data).decode(),
                'signing_id': result.signing_event.pk,
                'hash_before_prefix': result.signing_event.hash_before_prefix,
                'hash_after_prefix': result.signing_event.hash_after_prefix,
            }
            if signature_style:
                response_body['signature_style'] = signature_style
            return Response(response_body, status=status.HTTP_200_OK)

        # On-prem Basic Auth (no tenant audit)
        from .pdf_signing import (
            build_signing_dict,
            find_text_in_pdf,
            get_cn_from_certificate,
            get_indian_time_str,
            load_pfx_credentials,
            read_pfx_file,
            sign_pdf_at_positions,
        )
        from .signature_style import resolve_signature_style
        from endesive import pdf as endesive_pdf

        signature_style = resolve_signature_style()
        try:
            if pfx_path:
                pfx_data = read_pfx_file(pfx_path)
            else:
                pfx_data = decode_pfx_base64(pfx_b64)
            private_key, certificate, additional_certs = load_pfx_credentials(pfx_data, password)
        except (ValueError, Exception) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        text_positions = find_text_in_pdf(pdf_data, style=signature_style)
        if not text_positions:
            return Response(
                {'error': f'No position found for anchor text: {signature_style.anchor_text!r}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        indian_time_str, indian_time = get_indian_time_str()
        cn = get_cn_from_certificate(certificate)
        dct = build_signing_dict(cn, indian_time_str, indian_time, style=signature_style)
        try:
            signed_pdf_data = sign_pdf_at_positions(
                pdf_data,
                text_positions,
                dct,
                lambda data, position_dct: endesive_pdf.cms.sign(
                    data, position_dct, private_key, certificate, additional_certs, 'sha256',
                ),
                style=signature_style,
            )
        except Exception as exc:
            return Response({'error': f'Failed to sign PDF: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {
                'message': 'PDF signed successfully using PFX.',
                'signed_pdf_base64': base64.b64encode(signed_pdf_data).decode(),
            },
            status=status.HTTP_200_OK,
        )

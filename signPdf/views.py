import base64

from endesive import pdf
from rest_framework import serializers, status
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
    pfx_base64 = serializers.CharField(required=False, allow_blank=True)
    pfx_path = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField()

    def validate(self, data):
        pfx_b64 = (data.get('pfx_base64') or '').strip()
        pfx_path = (data.get('pfx_path') or '').strip()

        if bool(pfx_b64) == bool(pfx_path):
            raise serializers.ValidationError(
                'Provide exactly one of pfx_path or pfx_base64.'
            )

        data['pfx_base64'] = pfx_b64
        data['pfx_path'] = pfx_path
        return data


class PDFPfxSignAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PDFPfxSignSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        pdf_b64 = serializer.validated_data['pdf_base64']
        pfx_b64 = serializer.validated_data['pfx_base64']
        pfx_path = serializer.validated_data['pfx_path']
        password = serializer.validated_data['password']

        try:
            pdf_data = base64.b64decode(pdf_b64)
        except Exception as exc:
            return Response(
                {'error': f'Failed to decode base64 PDF data: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if pfx_path:
                pfx_data = read_pfx_file(pfx_path)
            else:
                pfx_data = base64.b64decode(pfx_b64)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {'error': f'Failed to decode base64 PFX data: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            private_key, certificate, additional_certs = load_pfx_credentials(pfx_data, password)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        text_positions = find_text_in_pdf(pdf_data, SIGNATURE_ANCHOR_TEXT)
        if not text_positions:
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
            return Response(
                {'error': f'Failed to sign PDF: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                'message': 'PDF signed successfully using PFX.',
                'signed_pdf_base64': base64.b64encode(signed_pdf_data).decode(),
            },
            status=status.HTTP_200_OK,
        )

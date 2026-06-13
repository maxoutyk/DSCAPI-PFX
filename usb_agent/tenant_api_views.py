import base64
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import APIKeyAuthentication
from accounts.permissions import IsAPIKeyAuthenticated
from accounts.services import TenantNotActiveError, ensure_tenant_can_sign
from signPdf.throttling import SignPdfBurstThrottle, SignPdfUserThrottle
from signPdf.validation import PdfValidationError, decode_pdf_base64

from .models import AgentDevice, UsbSignJob, UsbSignJobStatus
from .services import (
    SignJobError,
    build_job_status_payload,
    get_job_for_tenant,
    get_signed_pdf_from_job,
    prepare_usb_sign_job,
)


def _count_online_agents(tenant) -> int:
    timeout = getattr(settings, 'USB_AGENT_HEARTBEAT_TIMEOUT_SECONDS', 90)
    cutoff = timezone.now() - timedelta(seconds=timeout)
    return AgentDevice.objects.filter(
        tenant=tenant,
        revoked_at__isnull=True,
        last_seen_at__gte=cutoff,
    ).count()


class UsbSignCreateSerializer(serializers.Serializer):
    pdf_base64 = serializers.CharField()
    device_id = serializers.IntegerField()

    def validate_device_id(self, value):
        tenant = self.context['tenant']
        device = AgentDevice.objects.filter(
            pk=value,
            tenant=tenant,
            revoked_at__isnull=True,
        ).first()
        if not device:
            raise serializers.ValidationError('Agent device not found for this tenant.')
        return device


class TenantUsbSignMixin:
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated, IsAPIKeyAuthenticated]
    throttle_classes = [SignPdfBurstThrottle, SignPdfUserThrottle]

    def get_tenant_and_api_key(self, request):
        return request.user.tenant, request.user.api_key


class UsbSignCreateView(TenantUsbSignMixin, APIView):
    def post(self, request):
        tenant, api_key = self.get_tenant_and_api_key(request)
        try:
            ensure_tenant_can_sign(tenant)
        except TenantNotActiveError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        serializer = UsbSignCreateSerializer(
            data=request.data,
            context={'tenant': tenant},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            pdf_data = decode_pdf_base64(serializer.validated_data['pdf_base64'])
        except PdfValidationError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        device = serializer.validated_data['device_id']
        try:
            job = prepare_usb_sign_job(
                tenant=tenant,
                pdf_data=pdf_data,
                api_key=api_key,
                device=device,
            )
        except SignJobError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = build_job_status_payload(job)
        payload.update(
            {
                'message': (
                    'USB sign job prepared. Trigger the desktop agent on the PC with the '
                    'USB token, then poll this job until status is completed.'
                ),
                'agent_sign_url': 'http://127.0.0.1:9765/sign',
                'agents_online': _count_online_agents(tenant),
            },
        )
        return Response(payload, status=status.HTTP_201_CREATED)


class UsbSignDetailView(TenantUsbSignMixin, APIView):
    def get(self, request, job_id):
        tenant, _api_key = self.get_tenant_and_api_key(request)
        job = get_job_for_tenant(tenant, job_id)
        if not job:
            return Response({'error': 'Signing job not found.'}, status=status.HTTP_404_NOT_FOUND)

        payload = build_job_status_payload(job)
        if request.query_params.get('include_pdf') == '1' and job.status == UsbSignJobStatus.COMPLETED:
            signed_pdf = get_signed_pdf_from_job(job)
            if signed_pdf:
                payload['signed_pdf_base64'] = base64.b64encode(signed_pdf).decode('ascii')
        return Response(payload)


class UsbSignDownloadView(TenantUsbSignMixin, APIView):
    def get(self, request, job_id):
        tenant, _api_key = self.get_tenant_and_api_key(request)
        job = get_job_for_tenant(tenant, job_id)
        if not job:
            return Response({'error': 'Signing job not found.'}, status=status.HTTP_404_NOT_FOUND)
        if job.status != UsbSignJobStatus.COMPLETED:
            return Response(
                {'error': f'Job is not completed (status={job.status}).'},
                status=status.HTTP_409_CONFLICT,
            )

        signed_pdf = get_signed_pdf_from_job(job)
        if not signed_pdf:
            return Response({'error': 'Signed PDF is not available.'}, status=status.HTTP_404_NOT_FOUND)

        if request.query_params.get('format') == 'json':
            return Response(
                {
                    'job_id': str(job.id),
                    'signed_pdf_base64': base64.b64encode(signed_pdf).decode('ascii'),
                    'signing_id': job.signing_event_id,
                    'hash_after_prefix': (job.hash_after or '')[:8],
                },
            )

        response = HttpResponse(signed_pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="signed-{job.id}.pdf"'
        return response

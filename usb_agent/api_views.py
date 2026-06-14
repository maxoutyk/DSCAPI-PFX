import base64

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from signPdf.validation import PdfValidationError, decode_signed_pdf_base64

from .authentication import AgentDeviceAuthentication
from .services import (
    PairingCodeInvalidError,
    SignJobError,
    build_job_payload,
    complete_usb_sign_job,
    get_job_for_device,
    pair_device,
    record_heartbeat,
)
from .throttling import AgentHeartbeatThrottle, AgentJobThrottle, AgentPairThrottle


class AgentPairView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AgentPairThrottle]

    def post(self, request):
        code = (request.data.get('code') or '').strip()
        machine_name = (request.data.get('machine_name') or '').strip()
        agent_version = (request.data.get('agent_version') or '').strip()
        if not code:
            return Response({'error': 'Pairing code is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            device, device_token = pair_device(
                code=code,
                machine_name=machine_name,
                agent_version=agent_version,
            )
        except PairingCodeInvalidError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                'device_id': device.pk,
                'device_token': device_token,
                'tenant': device.tenant.name,
            },
            status=status.HTTP_201_CREATED,
        )


class AgentHeartbeatView(APIView):
    authentication_classes = [AgentDeviceAuthentication]
    throttle_classes = [AgentHeartbeatThrottle]

    def post(self, request):
        device = request.auth
        from django.utils.dateparse import parse_datetime

        cert_expires_raw = (request.data.get('cert_expires_at') or '').strip()
        cert_expires_at = parse_datetime(cert_expires_raw) if cert_expires_raw else None
        record_heartbeat(
            device,
            agent_version=(request.data.get('agent_version') or '').strip(),
            token_present=bool(request.data.get('token_present')),
            cert_cn=(request.data.get('cert_cn') or '').strip(),
            cert_expires_at=cert_expires_at,
        )
        return Response({'status': 'ok'})


class AgentSignJobDetailView(APIView):
    authentication_classes = [AgentDeviceAuthentication]
    throttle_classes = [AgentJobThrottle]

    def get(self, request, job_id):
        device = request.auth
        sign_token = (request.query_params.get('sign_token') or '').strip()
        try:
            job = get_job_for_device(device, job_id, sign_token=sign_token)
        except SignJobError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(build_job_payload(job))


class AgentSignJobCompleteView(APIView):
    authentication_classes = [AgentDeviceAuthentication]
    throttle_classes = [AgentJobThrottle]

    def post(self, request, job_id):
        device = request.auth
        signed_b64 = (request.data.get('signed_pdf_base64') or '').strip()
        sign_token = (request.data.get('sign_token') or '').strip()
        if not signed_b64:
            return Response({'error': 'signed_pdf_base64 is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            signed_pdf_data = decode_signed_pdf_base64(signed_b64)
        except PdfValidationError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            job = complete_usb_sign_job(device, job_id, signed_pdf_data, sign_token=sign_token)
        except SignJobError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                'job_id': str(job.id),
                'signing_id': job.signing_event_id,
                'hash_after': job.hash_after,
            },
        )

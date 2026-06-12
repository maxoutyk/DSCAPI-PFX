import base64
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from accounts.models import Tenant, TenantStatus
from accounts.services import QuotaExceededError, encrypt_pfx, record_signing_event
from signPdf.audit import SigningAuditMeta, sha256_hex
from signPdf.document_detection import detect_document_type
from signPdf.pdf_signing import find_text_in_pdf
from signPdf.signature_style import resolve_signature_style

from .models import AgentDevice, AgentPairingCode, UsbSignJob, UsbSignJobStatus


class AgentServiceError(Exception):
    pass


class PairingCodeInvalidError(AgentServiceError):
    pass


class DeviceRevokedError(AgentServiceError):
    pass


class SignJobError(AgentServiceError):
    pass


def hash_device_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


def generate_device_token() -> tuple[str, str, str]:
    secret = secrets.token_urlsafe(32)
    full_token = f'dsc_agent_{secret}'
    prefix = full_token[:16]
    return full_token, prefix, hash_device_token(full_token)


def generate_pairing_code() -> str:
    return f'{secrets.randbelow(1_000_000):06d}'


def create_pairing_code(*, tenant: Tenant, user: User) -> AgentPairingCode:
    ttl = getattr(settings, 'USB_AGENT_PAIRING_TTL_MINUTES', 5)
    AgentPairingCode.objects.filter(tenant=tenant, user=user, used_at__isnull=True).update(
        used_at=timezone.now(),
    )
    return AgentPairingCode.objects.create(
        tenant=tenant,
        user=user,
        code=generate_pairing_code(),
        expires_at=timezone.now() + timedelta(minutes=ttl),
    )


@transaction.atomic
def pair_device(*, code: str, machine_name: str, agent_version: str) -> tuple[AgentDevice, str]:
    pairing = (
        AgentPairingCode.objects.select_for_update()
        .select_related('tenant', 'user')
        .filter(code=code.strip(), used_at__isnull=True)
        .first()
    )
    if not pairing or not pairing.is_valid:
        raise PairingCodeInvalidError('Invalid or expired pairing code.')

    full_token, prefix, token_hash = generate_device_token()
    device = AgentDevice.objects.create(
        tenant=pairing.tenant,
        paired_by=pairing.user,
        label=(machine_name or '').strip()[:120],
        prefix=prefix,
        token_hash=token_hash,
        agent_version=(agent_version or '').strip()[:40],
        last_seen_at=timezone.now(),
    )
    pairing.used_at = timezone.now()
    pairing.save(update_fields=['used_at'])
    return device, full_token


def authenticate_device(raw_token: str) -> AgentDevice | None:
    if not raw_token or not raw_token.startswith('dsc_agent_'):
        return None
    prefix = raw_token[:16]
    token_hash = hash_device_token(raw_token)
    return (
        AgentDevice.objects.select_related('tenant')
        .filter(prefix=prefix, token_hash=token_hash, revoked_at__isnull=True)
        .first()
    )


def revoke_device(device: AgentDevice):
    device.revoked_at = timezone.now()
    device.save(update_fields=['revoked_at'])


def record_heartbeat(
    device: AgentDevice,
    *,
    agent_version: str = '',
    token_present: bool = False,
    cert_cn: str = '',
    cert_expires_at=None,
) -> AgentDevice:
    device.last_seen_at = timezone.now()
    if agent_version:
        device.agent_version = agent_version[:40]
    device.token_present = token_present
    device.cert_cn = (cert_cn or '')[:200]
    device.cert_expires_at = cert_expires_at
    device.save(
        update_fields=[
            'last_seen_at',
            'agent_version',
            'token_present',
            'cert_cn',
            'cert_expires_at',
        ],
    )
    return device


def _style_payload(tenant) -> dict:
    style = resolve_signature_style(tenant)
    return {
        'anchor_text': style.anchor_text,
        'font_size': style.font_size,
        'box_min_width': style.box_min_width,
        'box_height': style.box_height,
        'box_right_padding': style.box_right_padding,
        'box_shift_right': style.box_shift_right,
        'box_gap_above_label': style.box_gap_above_label,
        'box_shift_down_fitz': style.box_shift_down_fitz,
        'box_page_margin': style.box_page_margin,
        'icon_display_width': style.icon_display_width,
        'icon_overlap_inset': style.icon_overlap_inset,
        'icon_padding': style.icon_padding,
        'is_custom': style.is_custom,
    }


def _encrypt_pdf(pdf_data: bytes) -> bytes:
    return encrypt_pfx(pdf_data)


def _decrypt_pdf(encrypted: bytes) -> bytes:
    from accounts.services import decrypt_pfx

    return decrypt_pfx(encrypted)


@transaction.atomic
def prepare_usb_sign_job(*, tenant: Tenant, user: User, pdf_data: bytes) -> UsbSignJob:
    if tenant.status != TenantStatus.ACTIVE:
        raise SignJobError('Your account must be approved before signing documents.')

    style = resolve_signature_style(tenant)
    positions = find_text_in_pdf(pdf_data, style=style)
    if not positions:
        raise SignJobError(f"No position found for anchor text: {style.anchor_text!r}")

    detection = detect_document_type(pdf_data)
    ttl = getattr(settings, 'USB_AGENT_SIGN_JOB_TTL_MINUTES', 15)
    job = UsbSignJob.objects.create(
        tenant=tenant,
        user=user,
        encrypted_pdf=_encrypt_pdf(pdf_data),
        hash_before=sha256_hex(pdf_data),
        document_type=detection.document_type,
        detected_keyword=detection.detected_keyword,
        detection_confidence=detection.detection_confidence,
        placement_payload={
            'positions': positions,
            'style': _style_payload(tenant),
        },
        expires_at=timezone.now() + timedelta(minutes=ttl),
    )
    return job


def get_job_for_device(device: AgentDevice, job_id) -> UsbSignJob:
    job = (
        UsbSignJob.objects.select_related('tenant', 'user')
        .filter(pk=job_id, tenant=device.tenant, status=UsbSignJobStatus.PREPARED)
        .first()
    )
    if not job:
        raise SignJobError('Signing job not found.')
    if job.is_expired:
        job.status = UsbSignJobStatus.EXPIRED
        job.save(update_fields=['status'])
        raise SignJobError('Signing job expired.')
    if job.device_id and job.device_id != device.pk:
        raise SignJobError('Signing job is assigned to another agent.')
    if not job.device_id:
        job.device = device
        job.save(update_fields=['device'])
    return job


def build_job_payload(job: UsbSignJob) -> dict:
    pdf_data = _decrypt_pdf(job.encrypted_pdf)
    return {
        'job_id': str(job.id),
        'pdf_base64': base64.b64encode(pdf_data).decode('ascii'),
        'hash_before': job.hash_before,
        'document_type': job.document_type,
        'placement': job.placement_payload,
        'expires_at': job.expires_at.isoformat(),
    }


@transaction.atomic
def complete_usb_sign_job(device: AgentDevice, job_id, signed_pdf_data: bytes) -> UsbSignJob:
    job = get_job_for_device(device, job_id)
    hash_after = sha256_hex(signed_pdf_data)
    audit = SigningAuditMeta(
        hash_before=job.hash_before,
        hash_after=hash_after,
        document_type=job.document_type,
        detected_keyword=job.detected_keyword,
        detection_confidence=job.detection_confidence,
        endpoint='sign-usb',
        user=job.user,
    )
    try:
        signing_event = record_signing_event(job.tenant, success=True, audit=audit)
    except QuotaExceededError as exc:
        job.status = UsbSignJobStatus.FAILED
        job.error_message = str(exc)[:255]
        job.save(update_fields=['status', 'error_message'])
        raise SignJobError(str(exc)) from exc

    job.status = UsbSignJobStatus.COMPLETED
    job.hash_after = hash_after
    job.signing_event = signing_event
    job.completed_at = timezone.now()
    job.encrypted_pdf = _encrypt_pdf(signed_pdf_data)
    job.save(
        update_fields=[
            'status',
            'hash_after',
            'signing_event',
            'completed_at',
            'encrypted_pdf',
        ],
    )
    return job


def get_signed_pdf_from_job(job: UsbSignJob) -> bytes | None:
    if not job.encrypted_pdf:
        return None
    return _decrypt_pdf(job.encrypted_pdf)


def get_job_status_for_user(user: User, job_id) -> UsbSignJob | None:
    return (
        UsbSignJob.objects.select_related('signing_event', 'tenant')
        .filter(pk=job_id, user=user)
        .first()
    )

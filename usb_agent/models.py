import uuid

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from accounts.models import Tenant, UsageLog


class AgentDevice(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='agent_devices')
    paired_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paired_agent_devices',
    )
    label = models.CharField(max_length=120, blank=True)
    prefix = models.CharField(max_length=20, db_index=True)
    token_hash = models.CharField(max_length=64)
    agent_version = models.CharField(max_length=40, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    token_present = models.BooleanField(default=False)
    cert_cn = models.CharField(max_length=200, blank=True)
    cert_expires_at = models.DateTimeField(null=True, blank=True)
    paired_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-paired_at']

    def __str__(self):
        name = self.label or self.prefix
        return f'{name} ({self.tenant.name})'

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_online(self) -> bool:
        from django.conf import settings

        if self.is_revoked or not self.last_seen_at:
            return False
        timeout = getattr(settings, 'USB_AGENT_HEARTBEAT_TIMEOUT_SECONDS', 90)
        return (timezone.now() - self.last_seen_at).total_seconds() <= timeout


class AgentPairingCode(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='agent_pairing_codes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_pairing_codes')
    code = models.CharField(max_length=64, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and timezone.now() < self.expires_at


class UsbSignJobStatus(models.TextChoices):
    PREPARED = 'prepared', 'Prepared'
    COMPLETED = 'completed', 'Completed'
    EXPIRED = 'expired', 'Expired'
    FAILED = 'failed', 'Failed'


class UsbSignJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='usb_sign_jobs')
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='usb_sign_jobs',
        null=True,
        blank=True,
    )
    api_key = models.ForeignKey(
        'accounts.APIKey',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='usb_sign_jobs',
    )
    device = models.ForeignKey(
        AgentDevice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sign_jobs',
    )
    status = models.CharField(
        max_length=16,
        choices=UsbSignJobStatus.choices,
        default=UsbSignJobStatus.PREPARED,
    )
    encrypted_pdf = models.BinaryField()
    hash_before = models.CharField(max_length=64)
    hash_after = models.CharField(max_length=64, null=True, blank=True)
    document_type = models.CharField(max_length=32, null=True, blank=True)
    detected_keyword = models.CharField(max_length=100, null=True, blank=True)
    detection_confidence = models.CharField(max_length=8, default='none')
    placement_payload = models.JSONField()
    sign_token = models.CharField(max_length=64, blank=True, default='')
    signing_event = models.ForeignKey(
        UsageLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='usb_sign_jobs',
    )
    error_message = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

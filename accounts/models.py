import uuid
from calendar import monthrange
from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class TenantStatus(models.TextChoices):
    PENDING_EMAIL = 'pending_email', 'Pending email verification'
    PENDING_APPROVAL = 'pending_approval', 'Pending admin approval'
    ACTIVE = 'active', 'Active'
    SUSPENDED = 'suspended', 'Suspended'


class MembershipRole(models.TextChoices):
    OWNER = 'owner', 'Owner'
    MEMBER = 'member', 'Member'


def _next_month_start(now=None):
    now = now or timezone.now()
    year = now.year + (1 if now.month == 12 else 0)
    month = 1 if now.month == 12 else now.month + 1
    return timezone.make_aware(datetime(year, month, 1))


class Tenant(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    status = models.CharField(
        max_length=20,
        choices=TenantStatus.choices,
        default=TenantStatus.PENDING_EMAIL,
    )
    monthly_quota = models.PositiveIntegerField(default=100)
    usage_this_month = models.PositiveIntegerField(default=0)
    quota_reset_at = models.DateTimeField()
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_tenants',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.quota_reset_at:
            self.quota_reset_at = _next_month_start()
        super().save(*args, **kwargs)

    def reset_quota_if_needed(self):
        now = timezone.now()
        if now >= self.quota_reset_at:
            self.usage_this_month = 0
            self.quota_reset_at = _next_month_start(now)
            self.save(update_fields=['usage_this_month', 'quota_reset_at', 'updated_at'])

    @property
    def can_sign(self):
        return self.status == TenantStatus.ACTIVE

    @property
    def quota_remaining(self):
        self.reset_quota_if_needed()
        return max(0, self.monthly_quota - self.usage_this_month)


class TenantMembership(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tenant_memberships')
    role = models.CharField(max_length=20, choices=MembershipRole.choices, default=MembershipRole.OWNER)
    is_primary = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('tenant', 'user')]

    def __str__(self):
        return f'{self.user.email} → {self.tenant.name} ({self.role})'


class APIKey(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=20, db_index=True)
    key_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.prefix}...)'

    @property
    def is_active(self):
        return self.revoked_at is None


class StoredCertificate(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='certificates')
    alias = models.SlugField(max_length=80)
    encrypted_pfx = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('tenant', 'alias')]
        ordering = ['alias']

    def __str__(self):
        return f'{self.tenant.name}/{self.alias}'


class DocumentType(models.TextChoices):
    TAX_INVOICE = 'tax_invoice', 'Tax Invoice'
    PURCHASE_ORDER = 'purchase_order', 'Purchase Order'
    DELIVERY_CHALLAN = 'delivery_challan', 'Delivery Challan'
    CREDIT_NOTE = 'credit_note', 'Credit Note'
    DEBIT_NOTE = 'debit_note', 'Debit Note'
    PROFORMA_INVOICE = 'proforma_invoice', 'Proforma Invoice'
    QUOTATION = 'quotation', 'Quotation'
    UNKNOWN = 'unknown', 'Unknown'


class DetectionConfidence(models.TextChoices):
    HIGH = 'high', 'High'
    LOW = 'low', 'Low'
    NONE = 'none', 'None'


class TenantSignatureStyle(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='signature_style')
    is_enabled = models.BooleanField(
        default=False,
        help_text='When off, global platform defaults are used (existing API behaviour).',
    )
    anchor_text = models.CharField(
        max_length=120,
        blank=True,
        help_text='Text to search for in the PDF (e.g. Authorised Signatory). Leave blank to use platform default.',
    )
    font_size = models.PositiveSmallIntegerField(null=True, blank=True)
    box_min_width = models.PositiveSmallIntegerField(null=True, blank=True)
    box_height = models.PositiveSmallIntegerField(null=True, blank=True)
    box_right_padding = models.SmallIntegerField(null=True, blank=True)
    box_shift_right = models.SmallIntegerField(null=True, blank=True)
    box_gap_above_label = models.SmallIntegerField(null=True, blank=True)
    box_shift_down_fitz = models.SmallIntegerField(null=True, blank=True)
    box_page_margin = models.PositiveSmallIntegerField(null=True, blank=True)
    icon_display_width = models.PositiveSmallIntegerField(null=True, blank=True)
    icon_overlap_inset = models.PositiveSmallIntegerField(null=True, blank=True)
    icon_padding = models.PositiveSmallIntegerField(null=True, blank=True)
    custom_icon = models.ImageField(upload_to='signature_icons/%Y/%m/', blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tenant signature style'

    def __str__(self):
        state = 'custom' if self.is_enabled else 'default'
        return f'{self.tenant.name} ({state})'


class UsageLog(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='usage_logs')
    endpoint = models.CharField(max_length=100, default='signpdf-pfx')
    success = models.BooleanField(default=True)
    document_type = models.CharField(
        max_length=32,
        choices=DocumentType.choices,
        null=True,
        blank=True,
    )
    detected_keyword = models.CharField(max_length=100, null=True, blank=True)
    detection_confidence = models.CharField(
        max_length=8,
        choices=DetectionConfidence.choices,
        default=DetectionConfidence.NONE,
    )
    hash_before = models.CharField(max_length=64, null=True, blank=True)
    hash_after = models.CharField(max_length=64, null=True, blank=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    api_key = models.ForeignKey(
        'APIKey',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='usage_logs',
    )
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='signing_events',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Signing event'
        verbose_name_plural = 'Signing events'

    @property
    def hash_before_prefix(self) -> str:
        return (self.hash_before or '')[:8]

    @property
    def hash_after_prefix(self) -> str:
        return (self.hash_after or '')[:8]

    @property
    def signing_source(self) -> str:
        if self.endpoint == 'sign-portal':
            return 'browser'
        return 'api'

    def get_signing_source_display(self) -> str:
        return 'Browser' if self.signing_source == 'browser' else 'API'


class EmailVerificationToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_tokens')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Email token for {self.user.email}'


class PasswordResetToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Password reset for {self.user.email}'

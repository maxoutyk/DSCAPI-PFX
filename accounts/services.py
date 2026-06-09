import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from django.utils.text import slugify

from .models import (
    APIKey,
    EmailVerificationToken,
    MembershipRole,
    StoredCertificate,
    Tenant,
    TenantMembership,
    TenantStatus,
    UsageLog,
)


class QuotaExceededError(Exception):
    pass


class TenantNotActiveError(Exception):
    pass


def _fernet():
    key = settings.ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_pfx(pfx_bytes: bytes) -> bytes:
    return _fernet().encrypt(pfx_bytes)


def decrypt_pfx(encrypted: bytes) -> bytes:
    try:
        return _fernet().decrypt(encrypted)
    except InvalidToken as exc:
        raise ValueError('Failed to decrypt stored certificate') from exc


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    secret = secrets.token_urlsafe(32)
    full_key = f'dsc_live_{secret}'
    prefix = full_key[:16]
    return full_key, prefix, hash_api_key(full_key)


def unique_tenant_slug(name: str) -> str:
    base = slugify(name) or 'tenant'
    slug = base
    counter = 1
    while Tenant.objects.filter(slug=slug).exists():
        slug = f'{base}-{counter}'
        counter += 1
    return slug


@transaction.atomic
def register_tenant(*, email: str, password: str, organization_name: str) -> Tenant:
    if User.objects.filter(email__iexact=email).exists():
        raise ValueError('An account with this email already exists.')

    user = User.objects.create_user(
        username=email.lower(),
        email=email.lower(),
        password=password,
        is_active=False,
    )
    tenant = Tenant.objects.create(
        name=organization_name.strip(),
        slug=unique_tenant_slug(organization_name),
        status=TenantStatus.PENDING_EMAIL,
        monthly_quota=settings.DEFAULT_MONTHLY_QUOTA,
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=user,
        role=MembershipRole.OWNER,
        is_primary=True,
    )
    send_verification_email(user)
    return tenant


def send_verification_email(user: User):
    token = EmailVerificationToken.objects.create(user=user)
    verify_url = f'{settings.SITE_URL.rstrip("/")}/verify-email/{token.token}/'
    send_mail(
        subject='Verify your DSCAPI account',
        message=(
            f'Welcome to DSCAPI.\n\n'
            f'Click the link below to verify your email:\n{verify_url}\n\n'
            f'After verification, an administrator will review your account.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


@transaction.atomic
def verify_email(token_value) -> Tenant:
    token = EmailVerificationToken.objects.select_related('user').get(
        token=token_value,
        used_at__isnull=True,
    )
    user = token.user
    user.is_active = True
    user.save(update_fields=['is_active'])

    token.used_at = timezone_now()
    token.save(update_fields=['used_at'])

    membership = TenantMembership.objects.select_related('tenant').get(
        user=user,
        is_primary=True,
    )
    tenant = membership.tenant
    tenant.status = TenantStatus.PENDING_APPROVAL
    tenant.save(update_fields=['status', 'updated_at'])
    return tenant


def timezone_now():
    from django.utils import timezone

    return timezone.now()


def get_primary_tenant(user: User) -> Tenant | None:
    membership = (
        TenantMembership.objects.select_related('tenant')
        .filter(user=user, is_primary=True)
        .first()
    )
    return membership.tenant if membership else None


def create_api_key(tenant: Tenant, name: str) -> tuple[APIKey, str]:
    full_key, prefix, key_hash = generate_api_key()
    api_key = APIKey.objects.create(
        tenant=tenant,
        name=name.strip() or 'Default',
        prefix=prefix,
        key_hash=key_hash,
    )
    return api_key, full_key


def revoke_api_key(api_key: APIKey):
    from django.utils import timezone

    api_key.revoked_at = timezone.now()
    api_key.save(update_fields=['revoked_at'])


def authenticate_api_key(raw_key: str) -> tuple[APIKey, Tenant] | None:
    if not raw_key or not raw_key.startswith('dsc_live_'):
        return None

    prefix = raw_key[:16]
    key_hash = hash_api_key(raw_key)
    api_key = (
        APIKey.objects.select_related('tenant')
        .filter(prefix=prefix, key_hash=key_hash, revoked_at__isnull=True)
        .first()
    )
    if not api_key:
        return None

    from django.utils import timezone

    api_key.last_used_at = timezone.now()
    api_key.save(update_fields=['last_used_at'])
    return api_key, api_key.tenant


def store_certificate(tenant: Tenant, alias: str, pfx_bytes: bytes) -> StoredCertificate:
    alias = slugify(alias)
    if not alias:
        raise ValueError('Certificate alias is required.')

    encrypted = encrypt_pfx(pfx_bytes)
    cert, _created = StoredCertificate.objects.update_or_create(
        tenant=tenant,
        alias=alias,
        defaults={'encrypted_pfx': encrypted},
    )
    return cert


def get_stored_certificate_bytes(tenant: Tenant, alias: str) -> bytes:
    cert = StoredCertificate.objects.get(tenant=tenant, alias=alias)
    return decrypt_pfx(cert.encrypted_pfx)


def record_signing_usage(tenant: Tenant, *, success: bool = True):
    tenant.reset_quota_if_needed()
    if success:
        if tenant.usage_this_month >= tenant.monthly_quota:
            raise QuotaExceededError(
                f'Monthly quota exceeded ({tenant.monthly_quota} signs/month).'
            )
        tenant.usage_this_month += 1
        tenant.save(update_fields=['usage_this_month', 'updated_at'])
    UsageLog.objects.create(tenant=tenant, success=success)


def ensure_tenant_can_sign(tenant: Tenant):
    if not tenant.can_sign:
        if tenant.status == TenantStatus.PENDING_EMAIL:
            raise TenantNotActiveError('Verify your email before signing.')
        if tenant.status == TenantStatus.PENDING_APPROVAL:
            raise TenantNotActiveError('Your account is awaiting admin approval.')
        if tenant.status == TenantStatus.SUSPENDED:
            raise TenantNotActiveError('Your account has been suspended.')
        raise TenantNotActiveError('Your account is not active.')

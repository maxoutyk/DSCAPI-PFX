from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import EmailVerificationToken, PasswordResetToken, TenantStatus
from .services import get_primary_tenant


class EmailDeliveryError(Exception):
    pass


def is_smtp_configured() -> bool:
    return bool(getattr(settings, 'EMAIL_HOST', None))


def _build_verification_url(token: EmailVerificationToken) -> str:
    return f'{settings.SITE_URL.rstrip("/")}/verify-email/{token.token}/'


def send_verification_email(user: User) -> None:
    token = EmailVerificationToken.objects.create(user=user)
    verify_url = _build_verification_url(token)
    context = {
        'user': user,
        'verify_url': verify_url,
        'site_name': 'IG E-Sign',
    }

    subject = render_to_string('accounts/email/verify_email_subject.txt', context).strip()
    text_body = render_to_string('accounts/email/verify_email.txt', context)
    html_body = render_to_string('accounts/email/verify_email.html', context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, 'text/html')

    try:
        message.send(fail_silently=False)
    except Exception as exc:
        raise EmailDeliveryError('Failed to send verification email. Please try again later.') from exc


def resend_verification_email(email: str) -> bool:
    """
    Resend verification email for pending accounts.
    Returns True if an email was sent, False if the address is unknown (no enumeration).
    """
    normalized = email.strip().lower()
    user = User.objects.filter(email__iexact=normalized).first()
    if not user:
        return False

    if user.is_active:
        raise ValueError('This email address is already verified.')

    tenant = get_primary_tenant(user)
    if not tenant or tenant.status != TenantStatus.PENDING_EMAIL:
        raise ValueError('This account is not waiting for email verification.')

    EmailVerificationToken.objects.filter(user=user, used_at__isnull=True).delete()
    send_verification_email(user)
    return True


def _build_password_reset_url(token: PasswordResetToken) -> str:
    return f'{settings.SITE_URL.rstrip("/")}/reset-password/{token.token}/'


def send_password_reset_email(user: User) -> None:
    token = PasswordResetToken.objects.create(user=user)
    reset_url = _build_password_reset_url(token)
    context = {
        'user': user,
        'reset_url': reset_url,
        'site_name': 'IG E-Sign',
        'expiry_hours': settings.PASSWORD_RESET_TOKEN_HOURS,
    }

    subject = render_to_string('accounts/email/password_reset_subject.txt', context).strip()
    text_body = render_to_string('accounts/email/password_reset.txt', context)
    html_body = render_to_string('accounts/email/password_reset.html', context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, 'text/html')

    try:
        message.send(fail_silently=False)
    except Exception as exc:
        raise EmailDeliveryError('Failed to send password reset email. Please try again later.') from exc

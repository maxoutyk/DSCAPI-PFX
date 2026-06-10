from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .emailing import EmailDeliveryError, resend_verification_email
from .forms import (
    APIKeyForm,
    CertificateUploadForm,
    LoginForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    RegistrationForm,
    ResendVerificationForm,
)
from .models import TenantStatus
from .ratelimit import RATE_LIMIT_MESSAGE, is_rate_limited, record_rate_limit_hit
from .services import (
    PasswordResetTokenExpiredError,
    VerificationTokenExpiredError,
    create_api_key,
    get_primary_tenant,
    request_password_reset,
    reset_password_with_token,
    revoke_api_key,
    verify_email,
)


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'accounts/landing.html')


@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        if is_rate_limited(request, 'register'):
            messages.error(request, RATE_LIMIT_MESSAGE)
            return render(request, 'accounts/register.html', {'form': RegistrationForm()})

        form = RegistrationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                form.save()
            except ValueError as exc:
                form.add_error('email', str(exc))
            except EmailDeliveryError as exc:
                form.add_error(None, str(exc))
            else:
                return render(request, 'accounts/verify_email_sent.html', {'email': email})
        record_rate_limit_hit(request, 'register')
    else:
        form = RegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


@require_http_methods(['GET', 'POST'])
def resend_verification_view(request):
    email = request.GET.get('email', '').strip()
    if request.method == 'POST':
        if is_rate_limited(request, 'resend_verification'):
            messages.error(request, RATE_LIMIT_MESSAGE)
            return render(request, 'accounts/resend_verification.html', {'form': ResendVerificationForm()})

        form = ResendVerificationForm(request.POST)
        if form.is_valid():
            try:
                resend_verification_email(form.cleaned_data['email'])
            except ValueError as exc:
                form.add_error('email', str(exc))
            except EmailDeliveryError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, 'Verification email sent. Please check your inbox.')
                return render(
                    request,
                    'accounts/verify_email_sent.html',
                    {'email': form.cleaned_data['email']},
                )
        record_rate_limit_hit(request, 'resend_verification')
    else:
        form = ResendVerificationForm(initial={'email': email})

    return render(request, 'accounts/resend_verification.html', {'form': form})


def verify_email_view(request, token):
    try:
        tenant = verify_email(token)
    except VerificationTokenExpiredError:
        messages.error(
            request,
            'This verification link has expired. Request a new one from the sign-in page.',
        )
        return redirect('resend_verification')
    except Exception:
        messages.error(request, 'This verification link is invalid or has already been used.')
        return redirect('login')

    messages.success(
        request,
        f'Email verified for {tenant.name}. Your account is pending admin approval.',
    )
    return redirect('login')


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        if is_rate_limited(request, 'login'):
            messages.error(request, RATE_LIMIT_MESSAGE)
            return render(request, 'accounts/login.html', {'form': LoginForm()})

        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect('dashboard')
        record_rate_limit_hit(request, 'login')
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


@require_http_methods(['GET', 'POST'])
def password_reset_request_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        if is_rate_limited(request, 'password_reset'):
            messages.error(request, RATE_LIMIT_MESSAGE)
            return render(request, 'accounts/password_reset.html', {'form': PasswordResetRequestForm()})

        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            try:
                request_password_reset(form.cleaned_data['email'])
            except EmailDeliveryError as exc:
                form.add_error(None, str(exc))
            else:
                return render(
                    request,
                    'accounts/password_reset_done.html',
                    {
                        'email': form.cleaned_data['email'],
                        'expiry_hours': settings.PASSWORD_RESET_TOKEN_HOURS,
                    },
                )
        record_rate_limit_hit(request, 'password_reset')
    else:
        form = PasswordResetRequestForm()

    return render(request, 'accounts/password_reset.html', {'form': form})


@require_http_methods(['GET', 'POST'])
def password_reset_confirm_view(request, token):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = PasswordResetConfirmForm(request.POST)
        if form.is_valid():
            try:
                reset_password_with_token(token, form.cleaned_data['password'])
            except PasswordResetTokenExpiredError:
                messages.error(
                    request,
                    'This reset link has expired. Request a new password reset email.',
                )
                return redirect('password_reset')
            except Exception:
                messages.error(request, 'This reset link is invalid or has already been used.')
                return redirect('password_reset')
            else:
                messages.success(request, 'Your password has been reset. You can sign in now.')
                return redirect('login')
    else:
        form = PasswordResetConfirmForm()

    return render(request, 'accounts/password_reset_confirm.html', {'form': form, 'token': token})


@login_required
def dashboard_view(request):
    tenant = get_primary_tenant(request.user)
    return render(
        request,
        'accounts/dashboard.html',
        {
            'tenant': tenant,
            'usage_logs': tenant.usage_logs.all()[:20],
            'active_keys': tenant.api_keys.filter(revoked_at__isnull=True).count(),
            'cert_count': tenant.certificates.count(),
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def keys_view(request):
    tenant = get_primary_tenant(request.user)
    created_key = None

    if request.method == 'POST':
        if tenant.status != TenantStatus.ACTIVE:
            messages.error(request, 'Your account must be approved before creating API keys.')
        elif 'revoke' in request.POST:
            api_key = get_object_or_404(tenant.api_keys, pk=request.POST['revoke'], revoked_at__isnull=True)
            revoke_api_key(api_key)
            messages.success(request, f'Revoked API key "{api_key.name}".')
            return redirect('keys')
        else:
            form = APIKeyForm(request.POST)
            if form.is_valid():
                _api_key, created_key = create_api_key(tenant, form.cleaned_data['name'])
                return render(
                    request,
                    'accounts/key_created.html',
                    {'api_key': _api_key, 'full_key': created_key, 'tenant': tenant},
                )
    else:
        form = APIKeyForm()

    return render(
        request,
        'accounts/keys.html',
        {
            'tenant': tenant,
            'form': form,
            'api_keys': tenant.api_keys.all(),
            'created_key': created_key,
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def certs_view(request):
    tenant = get_primary_tenant(request.user)

    if request.method == 'POST':
        if tenant.status != TenantStatus.ACTIVE:
            messages.error(request, 'Your account must be approved before uploading certificates.')
        elif 'delete' in request.POST:
            cert = get_object_or_404(tenant.certificates, pk=request.POST['delete'])
            cert.delete()
            messages.success(request, f'Deleted certificate "{cert.alias}".')
            return redirect('certs')
        else:
            form = CertificateUploadForm(request.POST, request.FILES)
            if form.is_valid():
                form.save(tenant)
                messages.success(request, f'Saved certificate "{form.cleaned_data["alias"]}".')
                return redirect('certs')
    else:
        form = CertificateUploadForm()

    return render(
        request,
        'accounts/certs.html',
        {
            'tenant': tenant,
            'form': form,
            'certificates': tenant.certificates.all(),
        },
    )


@login_required
def docs_view(request):
    tenant = get_primary_tenant(request.user)
    return render(request, 'accounts/docs.html', {'tenant': tenant})

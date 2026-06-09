from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import APIKeyForm, CertificateUploadForm, LoginForm, RegistrationForm
from .models import TenantStatus
from .services import create_api_key, get_primary_tenant, revoke_api_key, verify_email


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            try:
                form.save()
            except ValueError as exc:
                form.add_error('email', str(exc))
            else:
                return render(request, 'accounts/verify_email_sent.html')
    else:
        form = RegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


def verify_email_view(request, token):
    try:
        tenant = verify_email(token)
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
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect('dashboard')
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard_view(request):
    tenant = get_primary_tenant(request.user)
    return render(request, 'accounts/dashboard.html', {'tenant': tenant})


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

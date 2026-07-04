from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .decorators import primary_tenant_required, tenant_owner_only, tenant_owner_required
from .emailing import EmailDeliveryError, resend_verification_email
from .forms import (
    APIKeyCustomerLabelForm,
    APIKeyForm,
    CertificateUploadForm,
    CompanyProfileForm,
    InviteRegisterForm,
    LoginForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    PortalSignForm,
    RegistrationForm,
    ResendVerificationForm,
    SignatureStyleForm,
    TeamInviteForm,
)
from .invites import (
    InviteError,
    accept_tenant_invite,
    create_tenant_invite,
    get_invite_by_token,
    list_pending_invites,
    register_invite_user,
    resend_tenant_invite,
    revoke_tenant_invite,
)
from .models import TenantSignatureStyle, TenantStatus
from .team import TeamError, list_tenant_memberships, remove_tenant_member
from .ratelimit import RATE_LIMIT_MESSAGE, is_rate_limited, record_rate_limit_hit
from .services import (
    PasswordResetTokenExpiredError,
    VerificationTokenExpiredError,
    create_api_key,
    get_company_profile,
    get_portal_sign_artifact,
    get_primary_tenant,
    build_monthly_usage_report,
    list_available_usage_periods,
    parse_usage_period_param,
    request_password_reset,
    reset_password_with_token,
    revoke_api_key,
    store_portal_sign_artifact,
    update_api_key_customer_label,
    user_is_tenant_owner,
    verify_email,
)


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'accounts/landing.html')


@require_http_methods(['GET'])
def public_api_docs_view(request):
    from .api_docs_catalog import build_api_docs_catalog

    base_url = request.build_absolute_uri('/').rstrip('/')
    catalog = build_api_docs_catalog(base_url)
    return render(
        request,
        'accounts/public_api_docs.html',
        {
            'catalog': catalog,
            'marketing_public_layout': True,
        },
    )


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
                sent = resend_verification_email(form.cleaned_data['email'])
            except ValueError as exc:
                form.add_error('email', str(exc))
            except EmailDeliveryError as exc:
                form.add_error(None, str(exc))
            else:
                record_rate_limit_hit(request, 'resend_verification')
                if sent:
                    messages.success(request, 'Verification email sent. Please check your inbox.')
                else:
                    messages.success(
                        request,
                        'If an account with that email is awaiting verification, we sent a new link.',
                    )
                return render(
                    request,
                    'accounts/verify_email_sent.html',
                    {'email': form.cleaned_data['email']},
                )
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
@primary_tenant_required
def dashboard_view(request):
    from django.db.models import Count
    from django.utils import timezone

    from gst.client import MyGSTCafeConfigError, get_platform_credentials

    from .models import DocumentType

    tenant = get_primary_tenant(request.user)
    profile = get_company_profile(tenant)
    partner_ready = True
    partner_error = ''
    try:
        get_platform_credentials()
    except MyGSTCafeConfigError as exc:
        partner_ready = False
        partner_error = str(exc)

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    type_labels = dict(DocumentType.choices)
    document_type_stats = [
        {
            'label': type_labels.get(row['document_type'], row['document_type']),
            'count': row['count'],
        }
        for row in (
            tenant.usage_logs.filter(
                success=True,
                document_type__isnull=False,
                created_at__gte=month_start,
            )
            .values('document_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
    ]

    member_usage = None
    if not user_is_tenant_owner(request.user):
        from gst.models import GstApiLog

        member_usage = {
            'signing_count': tenant.usage_logs.filter(
                success=True,
                created_at__gte=month_start,
            ).count(),
            'gst_count': GstApiLog.objects.filter(
                tenant=tenant,
                success=True,
                created_at__gte=month_start,
            ).count(),
        }

    return render(
        request,
        'accounts/dashboard.html',
        {
            'tenant': tenant,
            'quota': tenant.quota_state,
            'profile': profile,
            'partner_ready': partner_ready,
            'partner_error': partner_error,
            'usage_logs': tenant.usage_logs.select_related('user', 'api_key').all()[:20],
            'document_type_stats': document_type_stats,
            'active_keys': tenant.api_keys.filter(revoked_at__isnull=True).count(),
            'cert_count': tenant.certificates.count(),
            'member_usage': member_usage,
        },
    )


@login_required
@primary_tenant_required
@tenant_owner_required
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
        elif 'update_customer_label' in request.POST:
            api_key = get_object_or_404(tenant.api_keys, pk=request.POST['update_customer_label'])
            form = APIKeyCustomerLabelForm(request.POST)
            if form.is_valid():
                update_api_key_customer_label(api_key, form.cleaned_data['customer_label'])
                messages.success(request, f'Updated customer label for "{api_key.name}".')
            return redirect('keys')
        else:
            form = APIKeyForm(request.POST)
            if form.is_valid():
                _api_key, created_key = create_api_key(
                    tenant,
                    form.cleaned_data['name'],
                    customer_label=form.cleaned_data.get('customer_label', ''),
                )
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


def _usage_report_for_request(tenant, request):
    parsed = parse_usage_period_param(request.GET.get('period'))
    if parsed:
        year, month = parsed
        return build_monthly_usage_report(tenant, year=year, month=month)
    return build_monthly_usage_report(tenant)


@login_required
@primary_tenant_required
@tenant_owner_only
@require_http_methods(['GET'])
def usage_report_view(request):
    tenant = get_primary_tenant(request.user)
    report = _usage_report_for_request(tenant, request)
    chart_payload = {
        'daily_overall': report['daily_overall'],
        'customer_groups': report['customer_groups'],
    }
    return render(
        request,
        'accounts/usage_report.html',
        {
            'tenant': tenant,
            'report': report,
            'chart_payload': chart_payload,
            'period_options': list_available_usage_periods(tenant),
            'selected_period': report['period_key'],
        },
    )


@login_required
@primary_tenant_required
@tenant_owner_only
@require_http_methods(['GET'])
def usage_report_download_view(request):
    from django.http import HttpResponse

    from .usage_report_export import UsageReportDownloadError, build_usage_report_download

    tenant = get_primary_tenant(request.user)
    scope = request.GET.get('scope', 'overall')
    fmt = request.GET.get('format', 'csv').lower()

    try:
        payload, content_type, filename = build_usage_report_download(
            tenant,
            period=request.GET.get('period'),
            scope=scope,
            bucket=request.GET.get('bucket', '').strip(),
            customer_label=request.GET.get('customer', '').strip(),
            fmt=fmt,
        )
    except UsageReportDownloadError as exc:
        from django.http import Http404

        raise Http404(str(exc)) from exc

    response = HttpResponse(payload, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@primary_tenant_required
@tenant_owner_only
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
@primary_tenant_required
@tenant_owner_only
@require_http_methods(['GET', 'POST'])
def company_profile_view(request):
    tenant = get_primary_tenant(request.user)
    profile = get_company_profile(tenant)

    if request.method == 'POST':
        form = CompanyProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Company profile saved.')
            return redirect('company_profile')
    else:
        form = CompanyProfileForm(instance=profile)

    return render(
        request,
        'accounts/company_profile.html',
        {
            'tenant': tenant,
            'form': form,
            'profile': profile,
        },
    )


@login_required
@primary_tenant_required
@require_http_methods(['GET'])
def signature_style_view(request):
    from signPdf.signature_style import SignatureStyleConfig, resolve_signature_style

    tenant = get_primary_tenant(request.user)
    styles = tenant.signature_styles.all()
    return render(
        request,
        'accounts/signature.html',
        {
            'tenant': tenant,
            'styles': styles,
            'platform_defaults': SignatureStyleConfig.from_settings(),
            'resolved_style': resolve_signature_style(tenant),
        },
    )


@login_required
@primary_tenant_required
@tenant_owner_only
@require_http_methods(['GET', 'POST'])
def signature_style_edit_view(request, style_id=None):
    from signPdf.signature_style import SignatureStyleConfig, resolve_signature_style

    tenant = get_primary_tenant(request.user)
    platform_defaults = SignatureStyleConfig.from_settings()
    if style_id is None:
        style_obj = TenantSignatureStyle(tenant=tenant)
        page_title = 'New signature style'
    else:
        style_obj = get_object_or_404(TenantSignatureStyle, pk=style_id, tenant=tenant)
        page_title = f'Edit {style_obj.name}'

    if request.method == 'POST':
        if tenant.status != TenantStatus.ACTIVE:
            messages.error(request, 'Your account must be approved before changing signature styles.')
        else:
            form = SignatureStyleForm(request.POST, request.FILES, instance=style_obj, tenant=tenant)
            if form.is_valid():
                style = form.save(commit=False)
                style.tenant = tenant
                style.save()
                messages.success(request, f'Signature style “{style.name}” saved.')
                return redirect('signature_style')
    else:
        form = SignatureStyleForm(instance=style_obj, tenant=tenant)

    resolved = (
        resolve_signature_style(tenant, style_name=style_obj.name)
        if style_obj.pk and style_obj.is_enabled
        else platform_defaults
    )
    return render(
        request,
        'accounts/signature_edit.html',
        {
            'tenant': tenant,
            'form': form,
            'style_obj': style_obj,
            'page_title': page_title,
            'platform_defaults': platform_defaults,
            'resolved_style': resolved,
        },
    )


@login_required
@primary_tenant_required
@tenant_owner_required
@require_http_methods(['POST'])
def signature_style_delete_view(request, style_id):
    tenant = get_primary_tenant(request.user)
    if tenant.status != TenantStatus.ACTIVE:
        messages.error(request, 'Your account must be approved before changing signature styles.')
        return redirect('signature_style')

    style_obj = get_object_or_404(TenantSignatureStyle, pk=style_id, tenant=tenant)
    style_name = style_obj.name
    was_default = style_obj.is_default
    style_obj.delete()
    if was_default:
        replacement = tenant.signature_styles.order_by('name').first()
        if replacement is not None:
            replacement.is_default = True
            replacement.save(update_fields=['is_default'])
    messages.success(request, f'Signature style “{style_name}” deleted.')
    return redirect('signature_style')


@login_required
@primary_tenant_required
@tenant_owner_required
@require_http_methods(['POST'])
def signature_style_default_view(request, style_id):
    tenant = get_primary_tenant(request.user)
    if tenant.status != TenantStatus.ACTIVE:
        messages.error(request, 'Your account must be approved before changing signature styles.')
        return redirect('signature_style')

    style_obj = get_object_or_404(TenantSignatureStyle, pk=style_id, tenant=tenant)
    style_obj.is_default = True
    style_obj.save(update_fields=['is_default'])
    messages.success(request, f'“{style_obj.name}” is now the default signature style.')
    return redirect('signature_style')


@login_required
@primary_tenant_required
@tenant_owner_only
@require_http_methods(['GET', 'POST'])
def team_view(request):
    tenant = get_primary_tenant(request.user)
    invite_form = TeamInviteForm()

    if request.method == 'POST':
        if 'remove_member' in request.POST:
            membership_id = request.POST.get('remove_member')
            if membership_id:
                try:
                    removed_email = remove_tenant_member(
                        tenant=tenant,
                        membership_id=int(membership_id),
                        acting_user=request.user,
                    )
                except (TeamError, ValueError) as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Removed {removed_email} from your organization.')
            return redirect('team')

        if settings.TEAMS_ENABLED and 'send_invite' in request.POST:
            if is_rate_limited(request, 'team_invite'):
                messages.error(request, RATE_LIMIT_MESSAGE)
                return redirect('team')

            invite_form = TeamInviteForm(request.POST)
            if invite_form.is_valid():
                try:
                    create_tenant_invite(
                        tenant=tenant,
                        email=invite_form.cleaned_data['email'],
                        invited_by=request.user,
                    )
                except (InviteError, EmailDeliveryError) as exc:
                    messages.error(request, str(exc))
                else:
                    record_rate_limit_hit(request, 'team_invite')
                    messages.success(
                        request,
                        f'Invitation sent to {invite_form.cleaned_data["email"].strip().lower()}.',
                    )
            else:
                messages.error(request, 'Enter a valid email address.')
            return redirect('team')

        if settings.TEAMS_ENABLED and 'resend_invite' in request.POST:
            invite_id = request.POST.get('resend_invite')
            if invite_id:
                try:
                    invite = resend_tenant_invite(
                        tenant=tenant,
                        invite_id=invite_id,
                        acting_user=request.user,
                    )
                except (InviteError, EmailDeliveryError) as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Invitation resent to {invite.email}.')
            return redirect('team')

        if settings.TEAMS_ENABLED and 'revoke_invite' in request.POST:
            invite_id = request.POST.get('revoke_invite')
            if invite_id:
                try:
                    revoked_email = revoke_tenant_invite(
                        tenant=tenant,
                        invite_id=invite_id,
                        acting_user=request.user,
                    )
                except InviteError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Revoked invitation for {revoked_email}.')
            return redirect('team')

    memberships = list_tenant_memberships(tenant)
    context = {
        'tenant': tenant,
        'memberships': memberships,
        'owner_count': sum(1 for item in memberships if item.role == 'owner'),
        'invite_form': invite_form,
        'pending_invites': list_pending_invites(tenant) if settings.TEAMS_ENABLED else [],
    }
    return render(request, 'accounts/team.html', context)


@require_http_methods(['GET', 'POST'])
def team_invite_accept_view(request, token):
    if not settings.TEAMS_ENABLED:
        return render(request, 'accounts/invite_teams_disabled.html')

    invite = get_invite_by_token(token)
    if invite is None:
        messages.error(request, 'This invite link is invalid.')
        return redirect('login')

    if invite.revoked_at is not None:
        return render(
            request,
            'accounts/invite_unavailable.html',
            {'reason': 'This invite has been revoked. Ask the owner to send a new invite.'},
        )

    if invite.accepted_at is not None:
        if request.user.is_authenticated and invite.tenant.memberships.filter(user=request.user).exists():
            messages.info(request, f'You are already a member of {invite.tenant.name}.')
            return redirect('dashboard')
        return render(
            request,
            'accounts/invite_unavailable.html',
            {'reason': 'This invite has already been used.'},
        )

    from django.utils import timezone

    if timezone.now() > invite.expires_at:
        return render(
            request,
            'accounts/invite_unavailable.html',
            {
                'reason': 'This invite has expired. Ask the owner to send a new invite.',
                'tenant_name': invite.tenant.name,
            },
        )

    if request.user.is_authenticated:
        if request.user.email.lower() != invite.email.lower():
            return render(
                request,
                'accounts/invite_accept.html',
                {
                    'invite': invite,
                    'wrong_account': True,
                    'signed_in_email': request.user.email,
                },
            )

        if request.method == 'POST':
            try:
                accept_tenant_invite(invite=invite, user=request.user)
            except InviteError as exc:
                messages.error(request, str(exc))
                return redirect('dashboard')
            messages.success(request, f'You joined {invite.tenant.name}.')
            return redirect('dashboard')

        return render(
            request,
            'accounts/invite_accept.html',
            {
                'invite': invite,
                'accept_only': True,
            },
        )

    login_form = LoginForm(initial={'username': invite.email})
    register_form = InviteRegisterForm(initial={'email': invite.email})

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'login':
            if is_rate_limited(request, 'login'):
                messages.error(request, RATE_LIMIT_MESSAGE)
            else:
                login_form = LoginForm(request, data=request.POST)
                if login_form.is_valid():
                    user = login_form.get_user()
                    if user.email.lower() != invite.email.lower():
                        login_form.add_error(
                            None,
                            'Sign in with the email address that received the invite.',
                        )
                    else:
                        login(request, user)
                        try:
                            accept_tenant_invite(invite=invite, user=user)
                        except InviteError as exc:
                            messages.error(request, str(exc))
                            return redirect('dashboard')
                        messages.success(request, f'You joined {invite.tenant.name}.')
                        return redirect('dashboard')
                record_rate_limit_hit(request, 'login')
        elif action == 'register':
            if is_rate_limited(request, 'register'):
                messages.error(request, RATE_LIMIT_MESSAGE)
            else:
                register_form = InviteRegisterForm(request.POST)
                if register_form.is_valid():
                    try:
                        user = register_invite_user(
                            email=register_form.cleaned_data['email'],
                            password=register_form.cleaned_data['password'],
                        )
                        accept_tenant_invite(invite=invite, user=user)
                    except InviteError as exc:
                        register_form.add_error(None, str(exc))
                    except Exception:
                        register_form.add_error(None, 'Could not create your account. Try signing in instead.')
                    else:
                        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                        record_rate_limit_hit(request, 'register')
                        messages.success(request, f'Welcome to {invite.tenant.name}.')
                        return redirect('dashboard')
                record_rate_limit_hit(request, 'register')

    return render(
        request,
        'accounts/invite_accept.html',
        {
            'invite': invite,
            'login_form': login_form,
            'register_form': register_form,
        },
    )


@login_required
@primary_tenant_required
def docs_view(request):
    return redirect('public_api_docs')


@login_required
@primary_tenant_required
def docs_download_view(request):
    from django.http import HttpResponse
    from django.template.loader import render_to_string

    from .api_docs_pdf import PDF_MIMETYPE, markdown_to_pdf_bytes

    tenant = get_primary_tenant(request.user)
    content = render_to_string(
        'accounts/api-docs.md',
        {'tenant': tenant, 'quota': tenant.quota_state, 'request': request},
        request=request,
    )
    pdf_bytes = markdown_to_pdf_bytes(content)
    response = HttpResponse(pdf_bytes, content_type=PDF_MIMETYPE)
    response['Content-Disposition'] = 'attachment; filename="ig-esign-api-docs.pdf"'
    return response


@login_required
@primary_tenant_required
@require_http_methods(['GET', 'POST'])
def sign_view(request):
    import base64
    from datetime import timedelta

    from django.utils import timezone

    from signPdf.signing_service import (
        SigningFailure,
        analyze_pdf_for_signing,
        build_audit_for_http_request,
        record_signing_failure,
        sign_pdf_for_tenant,
    )

    tenant = get_primary_tenant(request.user)
    form = PortalSignForm(tenant=tenant)
    sign_result = None

    if request.method == 'POST':
        if is_rate_limited(request, 'portal_sign'):
            messages.error(request, RATE_LIMIT_MESSAGE)
        elif tenant.status != TenantStatus.ACTIVE:
            messages.error(request, 'Your account must be approved before signing documents.')
        else:
            form = PortalSignForm(request.POST, request.FILES, tenant=tenant)
            if form.is_valid():
                pdf_data = form.cleaned_data['pdf_file'].read()
                audit = build_audit_for_http_request(
                    request,
                    endpoint='sign-portal',
                    user=request.user,
                )
                try:
                    result = sign_pdf_for_tenant(
                        tenant=tenant,
                        pdf_data=pdf_data,
                        password=form.cleaned_data['password'],
                        cert_alias=form.cleaned_data['cert_alias'],
                        audit=audit,
                        signature_style_name=form.cleaned_data['signature_style'],
                    )
                except SigningFailure as exc:
                    if exc.record_failure:
                        if not audit.hash_before:
                            audit.populate_from_pdf(pdf_data)
                        record_signing_failure(tenant, audit)
                    messages.error(request, exc.message)
                else:
                    record_rate_limit_hit(request, 'portal_sign')
                    original_name = form.cleaned_data['pdf_file'].name
                    from signPdf.validation import safe_attachment_filename

                    stem = safe_attachment_filename(original_name, default='document.pdf').rsplit('.', 1)[0]
                    artifact = store_portal_sign_artifact(
                        tenant=tenant,
                        user=request.user,
                        signed_pdf_data=result.signed_pdf_data,
                        filename=f'{stem}-signed.pdf',
                        signing_event_id=result.signing_event.pk,
                        hash_before_prefix=result.signing_event.hash_before_prefix,
                        hash_after_prefix=result.signing_event.hash_after_prefix,
                        document_type_label=result.signing_event.get_document_type_display(),
                    )
                    request.session['portal_sign_artifact_id'] = str(artifact.id)
                    request.session.modified = True
                    return redirect('sign_done')

    return render(
        request,
        'accounts/sign.html',
        {
            'tenant': tenant,
            'form': form,
            'sign_result': sign_result,
            'has_certs': tenant.certificates.exists(),
        },
    )


@login_required
@primary_tenant_required
@require_http_methods(['POST'])
def sign_preview_view(request):
    from django.http import JsonResponse

    from signPdf.signing_service import SigningFailure, analyze_pdf_for_signing
    from signPdf.validation import PdfValidationError, validate_pdf_bytes

    tenant = get_primary_tenant(request.user)
    if tenant.status != TenantStatus.ACTIVE:
        return JsonResponse({'error': 'Account not active.'}, status=403)
    if is_rate_limited(request, 'portal_sign_preview'):
        return JsonResponse({'error': RATE_LIMIT_MESSAGE}, status=429)

    pdf_file = request.FILES.get('pdf_file')
    if not pdf_file:
        return JsonResponse({'error': 'PDF file is required.'}, status=400)
    if pdf_file.size > settings.PORTAL_SIGN_MAX_UPLOAD_BYTES:
        return JsonResponse({'error': 'PDF file is too large.'}, status=400)

    pdf_data = pdf_file.read()
    try:
        validate_pdf_bytes(pdf_data)
    except PdfValidationError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    signature_style = (request.POST.get('signature_style') or '').strip()
    try:
        analysis = analyze_pdf_for_signing(
            pdf_data,
            tenant,
            signature_style_name=signature_style,
        )
    except SigningFailure as exc:
        return JsonResponse({'error': exc.message}, status=400)
    record_rate_limit_hit(request, 'portal_sign_preview')

    return JsonResponse({
        'page_count': analysis.page_count,
        'signature_slots': analysis.signature_slots,
        'anchor_text': analysis.anchor_text,
        'document_type_label': analysis.document_type_label,
        'ready': analysis.ready,
    })


def _get_portal_sign_download(request):
    artifact_id = request.session.get('portal_sign_artifact_id')
    if not artifact_id:
        return None
    loaded = get_portal_sign_artifact(user=request.user, artifact_id=artifact_id)
    if not loaded:
        request.session.pop('portal_sign_artifact_id', None)
        request.session.modified = True
        return None
    pdf_data, metadata = loaded
    return {'data': pdf_data, **metadata}


@login_required
@primary_tenant_required
def sign_done_view(request):
    payload = _get_portal_sign_download(request)
    if not payload:
        messages.error(request, 'Download link expired. Please sign the document again.')
        return redirect('sign')
    display = {key: value for key, value in payload.items() if key != 'data'}
    return render(request, 'accounts/sign_done.html', {'result': display})


@login_required
@primary_tenant_required
def sign_download_view(request):
    from django.http import HttpResponse

    from signPdf.validation import safe_attachment_filename

    payload = _get_portal_sign_download(request)
    if not payload:
        messages.error(request, 'Download link expired. Please sign the document again.')
        return redirect('sign')

    response = HttpResponse(
        payload['data'],
        content_type='application/pdf',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{safe_attachment_filename(payload["filename"])}"'
    )
    return response

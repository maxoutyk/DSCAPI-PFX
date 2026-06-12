from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.models import TenantStatus
from accounts.services import get_primary_tenant

from .models import AgentDevice, UsbSignJob, UsbSignJobStatus
from .services import SignJobError, create_pairing_code, prepare_usb_sign_job, revoke_device


@login_required
@require_http_methods(['GET'])
def agent_view(request):
    tenant = get_primary_tenant(request.user)
    devices = tenant.agent_devices.all() if tenant else AgentDevice.objects.none()
    return render(
        request,
        'usb_agent/agent.html',
        {
            'tenant': tenant,
            'devices': devices,
            'agent_local_port': settings.USB_AGENT_LOCAL_PORT,
            'site_url': settings.SITE_URL,
        },
    )


@login_required
@require_http_methods(['POST'])
def agent_pair_code_view(request):
    tenant = get_primary_tenant(request.user)
    if not tenant or tenant.status != TenantStatus.ACTIVE:
        messages.error(request, 'Your account must be active to pair an agent.')
        return redirect('usb_agent')

    pairing = create_pairing_code(tenant=tenant, user=request.user)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(
            {
                'code': pairing.code,
                'expires_at': pairing.expires_at.isoformat(),
            },
        )
    messages.success(
        request,
        f'Pairing code: {pairing.code} (expires in 5 minutes). Enter it in the IG E-Sign Agent installer.',
    )
    return redirect('usb_agent')


@login_required
@require_http_methods(['POST'])
def agent_revoke_view(request, device_id):
    tenant = get_primary_tenant(request.user)
    device = get_object_or_404(AgentDevice, pk=device_id, tenant=tenant)
    revoke_device(device)
    messages.success(request, f'Revoked agent "{device.label or device.prefix}".')
    return redirect('usb_agent')


@login_required
@require_http_methods(['GET', 'POST'])
def sign_usb_view(request):
    from .forms import UsbSignForm

    tenant = get_primary_tenant(request.user)
    form = UsbSignForm()
    active_job = None

    if request.method == 'POST':
        if tenant.status != TenantStatus.ACTIVE:
            messages.error(request, 'Your account must be approved before signing documents.')
        else:
            form = UsbSignForm(request.POST, request.FILES)
            if form.is_valid():
                pdf_data = form.cleaned_data['pdf_file'].read()
                try:
                    job = prepare_usb_sign_job(tenant=tenant, user=request.user, pdf_data=pdf_data)
                except SignJobError as exc:
                    messages.error(request, str(exc))
                else:
                    request.session['usb_sign_job_id'] = str(job.id)
                    request.session['usb_sign_filename'] = form.cleaned_data['pdf_file'].name
                    return redirect('usb_sign_pending', job_id=job.id)

    job_id = request.session.get('usb_sign_job_id')
    if job_id:
        active_job = UsbSignJob.objects.filter(pk=job_id, user=request.user).first()

    return render(
        request,
        'usb_agent/sign_usb.html',
        {
            'tenant': tenant,
            'form': form,
            'active_job': active_job,
            'has_paired_agent': tenant.agent_devices.filter(revoked_at__isnull=True).exists() if tenant else False,
            'agent_local_port': settings.USB_AGENT_LOCAL_PORT,
        },
    )


@login_required
@require_http_methods(['GET'])
def sign_usb_pending_view(request, job_id):
    job = get_object_or_404(UsbSignJob, pk=job_id, user=request.user)
    if job.is_expired and job.status == UsbSignJobStatus.PREPARED:
        job.status = UsbSignJobStatus.EXPIRED
        job.save(update_fields=['status'])
    return render(
        request,
        'usb_agent/sign_usb_pending.html',
        {
            'job': job,
            'filename': request.session.get('usb_sign_filename', 'document.pdf'),
            'agent_local_port': settings.USB_AGENT_LOCAL_PORT,
            'site_url': settings.SITE_URL,
        },
    )


@login_required
@require_http_methods(['GET'])
def sign_usb_status_view(request, job_id):
    job = get_object_or_404(UsbSignJob, pk=job_id, user=request.user)
    payload = {
        'status': job.status,
        'signing_id': job.signing_event_id,
        'hash_before_prefix': (job.hash_before or '')[:8],
        'hash_after_prefix': (job.hash_after or '')[:8] if job.hash_after else '',
        'error': job.error_message,
    }
    return JsonResponse(payload)


@login_required
@require_http_methods(['GET'])
def sign_usb_done_view(request, job_id):
    job = get_object_or_404(
        UsbSignJob,
        pk=job_id,
        user=request.user,
        status=UsbSignJobStatus.COMPLETED,
    )
    display = {
        'signing_id': job.signing_event_id,
        'hash_before_prefix': (job.hash_before or '')[:8],
        'hash_after_prefix': (job.hash_after or '')[:8],
        'filename': request.session.get('usb_sign_filename', 'document-signed.pdf'),
        'document_type_label': job.signing_event.get_document_type_display() if job.signing_event else '—',
    }
    request.session['usb_sign_download'] = {
        'job_id': str(job.id),
        'expires_at': (timezone.now() + timedelta(minutes=15)).isoformat(),
    }
    request.session.modified = True
    return render(request, 'usb_agent/sign_usb_done.html', {'result': display})


@login_required
@require_http_methods(['GET'])
def sign_usb_download_view(request):
    job_id = request.session.get('usb_sign_download', {}).get('job_id')
    if not job_id:
        messages.error(request, 'Download expired. Please sign again.')
        return redirect('usb_sign')

    job = get_object_or_404(
        UsbSignJob,
        pk=job_id,
        user=request.user,
        status=UsbSignJobStatus.COMPLETED,
    )
    from .services import get_signed_pdf_from_job

    pdf_data = get_signed_pdf_from_job(job)
    if not pdf_data:
        messages.error(request, 'Signed file is no longer available.')
        return redirect('usb_sign')

    stem = request.session.get('usb_sign_filename', 'document.pdf').rsplit('.', 1)[0]
    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{stem}-signed.pdf"'
    return response

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts.decorators import primary_tenant_required, tenant_owner_only
from accounts.services import get_company_profile, get_primary_tenant, nic_portal_credentials_configured

from .client import MyGSTCafeConfigError, get_platform_credentials
from .portal_catalog import GST_ENDPOINT_ORDER, GST_PRINT_ENDPOINTS, build_gst_portal_endpoints


def _gst_portal_context(request, *, endpoint_id: str | None = None) -> dict:
    tenant = get_primary_tenant(request.user)
    profile = get_company_profile(tenant)
    partner_ready = True
    partner_error = ''
    try:
        get_platform_credentials()
    except MyGSTCafeConfigError as exc:
        partner_ready = False
        partner_error = str(exc)

    base_url = request.build_absolute_uri('/').rstrip('/')
    portal_data = build_gst_portal_endpoints(
        base_url,
        gstin=profile.gstin or '',
        fy='2024-25',
    )
    endpoints = portal_data['endpoints']
    active_endpoint = None
    if endpoint_id:
        active_endpoint = next((ep for ep in endpoints if ep['id'] == endpoint_id), None)
    elif endpoints:
        active_endpoint = endpoints[0]

    return {
        'tenant': tenant,
        'profile': profile,
        'partner_ready': partner_ready,
        'partner_error': partner_error,
        'endpoints': endpoints,
        'active_endpoint': active_endpoint,
        'defaults': portal_data['defaults'],
        'gst_try_url': reverse('gst_portal_try'),
        'gst_service_path_prefix': '/dashboard/gst/',
        'nic_credentials_configured': nic_portal_credentials_configured(profile),
        'requires_nic_credentials': bool(
            active_endpoint and active_endpoint['id'] in GST_PRINT_ENDPOINTS
        ),
    }


@login_required
@primary_tenant_required
@tenant_owner_only
@require_http_methods(['GET'])
def gst_dashboard_view(request):
    if GST_ENDPOINT_ORDER:
        return redirect('gst_service', endpoint_id=GST_ENDPOINT_ORDER[0])
    return render(request, 'gst/dashboard.html', _gst_portal_context(request))


@login_required
@primary_tenant_required
@tenant_owner_only
@require_http_methods(['GET'])
def gst_service_view(request, endpoint_id: str):
    if endpoint_id not in GST_ENDPOINT_ORDER:
        raise Http404('Unknown GST service.')
    context = _gst_portal_context(request, endpoint_id=endpoint_id)
    if context['active_endpoint'] is None:
        raise Http404('GST service is not available.')
    return render(request, 'gst/dashboard.html', context)

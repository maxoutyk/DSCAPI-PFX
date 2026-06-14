from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts.decorators import primary_tenant_required
from accounts.services import get_company_profile, get_primary_tenant

from .client import MyGSTCafeConfigError, get_platform_credentials
from .portal_catalog import build_gst_portal_endpoints


@login_required
@primary_tenant_required
@require_http_methods(['GET'])
def gst_dashboard_view(request):
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

    return render(
        request,
        'gst/dashboard.html',
        {
            'tenant': tenant,
            'profile': profile,
            'partner_ready': partner_ready,
            'partner_error': partner_error,
            'endpoints': portal_data['endpoints'],
            'defaults': portal_data['defaults'],
            'gst_try_url': reverse('gst_portal_try'),
        },
    )

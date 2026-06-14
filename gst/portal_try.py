from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from accounts.decorators import primary_tenant_required
from accounts.services import get_primary_tenant, user_is_tenant_owner

from .lookup_handlers import execute_portal_endpoint
from .portal_ratelimit import GST_PORTAL_RATE_LIMIT_MESSAGE, is_gst_portal_rate_limited


@login_required
@primary_tenant_required
@require_POST
def gst_portal_try_view(request):
    if not user_is_tenant_owner(request.user):
        return JsonResponse(
            {'error': 'Only organization owners can run GST lookups.'},
            status=403,
        )

    tenant = get_primary_tenant(request.user)
    if is_gst_portal_rate_limited(tenant.pk):
        return JsonResponse({'error': GST_PORTAL_RATE_LIMIT_MESSAGE}, status=429)

    endpoint_id = (request.POST.get('endpoint') or '').strip()
    if not endpoint_id:
        return JsonResponse({'error': 'endpoint is required.'}, status=400)

    params = {
        key: value
        for key, value in request.POST.items()
        if key not in {'endpoint', 'csrfmiddlewaretoken'}
    }
    status_code, body = execute_portal_endpoint(
        endpoint_id=endpoint_id,
        tenant=tenant,
        request=request,
        query_params=params,
    )
    tenant.refresh_from_db()
    response = JsonResponse(body, status=status_code, safe=False)
    response['X-GST-Quota-Remaining'] = str(tenant.gst_quota_remaining)
    return response

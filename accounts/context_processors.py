from django.conf import settings


def google_ads(request):
    return {'google_ads_id': getattr(settings, 'GOOGLE_ADS_ID', '')}


def csp_nonce(request):
    return {'csp_nonce': getattr(request, 'csp_nonce', '')}


def portal_nav(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    from .services import user_is_tenant_owner

    return {
        'portal_is_owner': user_is_tenant_owner(request.user),
        'teams_enabled': getattr(settings, 'TEAMS_ENABLED', False),
    }

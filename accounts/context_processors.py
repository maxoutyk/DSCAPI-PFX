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


def seo(request):
    from .marketing_views import get_structured_data_for_view
    from .seo import (
        BRAND_NAME,
        OG_IMAGE_ALT,
        OG_IMAGE_HEIGHT,
        OG_IMAGE_WIDTH,
        PRODUCT_NAME,
        TAGLINE,
        build_canonical_url,
        og_image_url,
        page_meta_for_request,
        should_noindex,
    )

    meta = page_meta_for_request(request)
    noindex = should_noindex(request)
    view_name = ''
    if getattr(request, 'resolver_match', None) and request.resolver_match:
        view_name = request.resolver_match.url_name or ''
    return {
        'seo_brand_name': BRAND_NAME,
        'seo_product_name': PRODUCT_NAME,
        'seo_tagline': TAGLINE,
        'seo_page_title': meta['title'],
        'seo_meta_description': meta['description'],
        'seo_canonical_url': build_canonical_url(request),
        'seo_robots': 'noindex, nofollow' if noindex else 'index, follow',
        'seo_og_image': og_image_url(),
        'seo_og_image_width': OG_IMAGE_WIDTH,
        'seo_og_image_height': OG_IMAGE_HEIGHT,
        'seo_og_image_alt': OG_IMAGE_ALT,
        'seo_og_type': 'article' if view_name == 'blog_post' else 'website',
        'seo_structured_data': get_structured_data_for_view(request),
        'google_site_verification': getattr(settings, 'GOOGLE_SITE_VERIFICATION', ''),
    }

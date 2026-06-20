from django.conf import settings


def google_ads(request):
    return {'google_ads_id': getattr(settings, 'GOOGLE_ADS_ID', '')}


def csp_nonce(request):
    return {'csp_nonce': getattr(request, 'csp_nonce', '')}

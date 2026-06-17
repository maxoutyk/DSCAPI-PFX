from django.conf import settings


def google_ads(request):
    return {'google_ads_id': getattr(settings, 'GOOGLE_ADS_ID', '')}

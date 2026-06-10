from zoneinfo import ZoneInfo

from django import template
from django.conf import settings
from django.utils import timezone
from django.utils.formats import date_format

register = template.Library()

DISPLAY_TZ = ZoneInfo(getattr(settings, 'DISPLAY_TIME_ZONE', 'Asia/Kolkata'))


@register.filter
def ist(value, arg='M j, H:i'):
    """Format an aware datetime in the portal display timezone (IST by default)."""
    if not value:
        return ''
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.utc)
    local = timezone.localtime(value, DISPLAY_TZ)
    return date_format(local, arg, use_l10n=False)

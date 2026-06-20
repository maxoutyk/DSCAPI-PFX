from __future__ import annotations

from .portal_catalog import GST_ENDPOINT_ORDER, PORTAL_UI


def gst_sidebar(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}

    nav = [
        {
            'id': endpoint_id,
            'label': PORTAL_UI.get(endpoint_id, {}).get('tab', endpoint_id),
        }
        for endpoint_id in GST_ENDPOINT_ORDER
    ]
    path = getattr(request, 'path', '') or ''
    return {
        'gst_sidebar_nav': nav,
        'gst_nav_open': path.startswith('/dashboard/gst'),
    }

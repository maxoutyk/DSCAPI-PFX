from django.urls import path

from . import api_views

urlpatterns = [
    path('gst/gstin/search/', api_views.GstinSearchView.as_view(), name='gst_gstin_search'),
    path('gst/preference/', api_views.GstPreferenceView.as_view(), name='gst_preference'),
    path('gst/returns/', api_views.GstReturnStatusView.as_view(), name='gst_return_status'),
    path('gst/eway/print/', api_views.GstEwayPrintView.as_view(), name='gst_eway_print'),
    path('gst/einvoice/print/', api_views.GstIrnPrintView.as_view(), name='gst_irn_print'),
]

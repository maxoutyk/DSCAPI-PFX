from django.contrib import admin

from .models import GstApiLog


@admin.register(GstApiLog)
class GstApiLogAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'endpoint', 'success', 'gstin', 'client_ip', 'api_key', 'created_at')
    list_filter = ('success', 'endpoint')
    search_fields = ('tenant__name', 'gstin')
    readonly_fields = ('tenant', 'endpoint', 'success', 'gstin', 'client_ip', 'api_key', 'meta', 'created_at')

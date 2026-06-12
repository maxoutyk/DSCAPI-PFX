from django.contrib import admin

from .models import AgentDevice, AgentPairingCode, UsbSignJob


@admin.register(AgentDevice)
class AgentDeviceAdmin(admin.ModelAdmin):
    list_display = ('label', 'tenant', 'prefix', 'agent_version', 'last_seen_at', 'token_present', 'revoked_at')
    list_filter = ('revoked_at', 'token_present')
    search_fields = ('label', 'prefix', 'tenant__name', 'cert_cn')
    readonly_fields = ('prefix', 'token_hash', 'paired_at', 'paired_by')


@admin.register(AgentPairingCode)
class AgentPairingCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'tenant', 'user', 'expires_at', 'used_at', 'created_at')
    search_fields = ('code', 'tenant__name', 'user__email')


@admin.register(UsbSignJob)
class UsbSignJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'user', 'device', 'status', 'hash_before', 'created_at', 'completed_at')
    list_filter = ('status',)
    search_fields = ('hash_before', 'hash_after', 'tenant__name')
    readonly_fields = ('encrypted_pdf',)

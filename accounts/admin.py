from django.contrib import admin, messages
from django.utils import timezone

from .models import (
    APIKey,
    EmailVerificationToken,
    PasswordResetToken,
    StoredCertificate,
    Tenant,
    TenantMembership,
    TenantSignatureStyle,
    UsageLog,
)
from .models import TenantStatus


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'status', 'usage_this_month', 'monthly_quota', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'slug')
    readonly_fields = ('created_at', 'updated_at', 'approved_at', 'approved_by')
    actions = ['approve_tenants', 'suspend_tenants']

    @admin.action(description='Approve selected tenants')
    def approve_tenants(self, request, queryset):
        updated = queryset.filter(status=TenantStatus.PENDING_APPROVAL).update(
            status=TenantStatus.ACTIVE,
            approved_at=timezone.now(),
            approved_by=request.user,
        )
        self.message_user(request, f'Approved {updated} tenant(s).', messages.SUCCESS)

    @admin.action(description='Suspend selected tenants')
    def suspend_tenants(self, request, queryset):
        updated = queryset.exclude(status=TenantStatus.SUSPENDED).update(status=TenantStatus.SUSPENDED)
        self.message_user(request, f'Suspended {updated} tenant(s).', messages.WARNING)


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'tenant', 'role', 'is_primary', 'created_at')
    list_filter = ('role', 'is_primary')


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ('name', 'prefix', 'tenant', 'created_at', 'last_used_at', 'revoked_at')
    list_filter = ('revoked_at',)
    search_fields = ('name', 'prefix', 'tenant__name')


@admin.register(StoredCertificate)
class StoredCertificateAdmin(admin.ModelAdmin):
    list_display = ('alias', 'tenant', 'created_at')
    search_fields = ('alias', 'tenant__name')


@admin.register(TenantSignatureStyle)
class TenantSignatureStyleAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'name', 'is_default', 'is_enabled', 'anchor_text', 'updated_at')
    list_filter = ('is_enabled', 'is_default')
    search_fields = ('tenant__name', 'name', 'anchor_text')


@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    list_display = (
        'tenant',
        'endpoint',
        'document_type',
        'success',
        'client_ip',
        'api_key',
        'user',
        'hash_before',
        'hash_after',
        'created_at',
    )
    list_filter = ('success', 'endpoint', 'document_type', 'detection_confidence')
    search_fields = ('hash_before', 'hash_after', 'client_ip', 'tenant__name')
    readonly_fields = (
        'tenant',
        'endpoint',
        'success',
        'document_type',
        'detected_keyword',
        'detection_confidence',
        'hash_before',
        'hash_after',
        'client_ip',
        'api_key',
        'user',
        'created_at',
    )


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'used_at')
    readonly_fields = ('token',)


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'used_at')
    readonly_fields = ('token',)

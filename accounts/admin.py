from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils import timezone

from .admin_forms import GrantQuotaEntitlementForm, RenewQuotaEntitlementForm
from .models import (
    APIKey,
    CompanyProfile,
    EmailVerificationToken,
    PasswordResetToken,
    QuotaEntitlement,
    QuotaEntitlementStatus,
    QuotaPlan,
    StoredCertificate,
    Tenant,
    TenantMembership,
    TenantSignatureStyle,
    UsageLog,
)
from .models import TenantStatus
from .quota import grant_entitlement, preview_renew_entitlement, renew_entitlement, resolve_quota_state
from .services import revoke_api_key


class QuotaEntitlementInline(admin.TabularInline):
    model = QuotaEntitlement
    extra = 0
    can_delete = False
    fields = (
        'plan_at_grant',
        'quota_limit',
        'usage_count',
        'inline_remaining',
        'carry_forward',
        'starts_at',
        'ends_at',
        'status',
    )
    readonly_fields = fields
    ordering = ('-starts_at',)
    verbose_name_plural = 'Quota entitlement history'

    @admin.display(description='Remaining')
    def inline_remaining(self, obj):
        return obj.remaining

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    change_form_template = 'admin/accounts/tenant/change_form.html'
    inlines = [QuotaEntitlementInline]
    list_display = (
        'name',
        'slug',
        'status',
        'quota_plan',
        'quota_usage_summary',
        'monthly_quota',
        'created_at',
    )
    list_filter = ('status', 'quota_plan')
    search_fields = ('name', 'slug')
    readonly_fields = (
        'created_at',
        'updated_at',
        'approved_at',
        'approved_by',
        'active_quota_summary',
    )
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'status'),
        }),
        ('Quota', {
            'fields': (
                'quota_plan',
                'active_quota_summary',
                'monthly_quota',
                'usage_this_month',
                'quota_reset_at',
            ),
        }),
        ('Approval', {
            'fields': ('approved_at', 'approved_by'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )
    actions = [
        'approve_tenants',
        'suspend_tenants',
        'reactivate_tenants',
        'grant_quota_action',
        'renew_quota_action',
    ]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/grant-quota/',
                self.admin_site.admin_view(self.grant_quota_view),
                name='accounts_tenant_grant_quota',
            ),
            path(
                '<path:object_id>/renew-quota/',
                self.admin_site.admin_view(self.renew_quota_view),
                name='accounts_tenant_renew_quota',
            ),
        ]
        return custom_urls + urls

    @admin.display(description='Quota usage')
    def quota_usage_summary(self, obj):
        state = resolve_quota_state(obj)
        return f'{state.used}/{state.limit}'

    @admin.display(description='Active quota')
    def active_quota_summary(self, obj):
        if obj is None:
            return '—'
        state = resolve_quota_state(obj)
        if state.is_term_based:
            return format_html(
                '<strong>{}</strong> plan — {}/{} used, {} remaining — expires {}',
                state.plan.upper().replace('_', '+'),
                state.used,
                state.limit,
                state.remaining,
                state.resets_or_expires_at.strftime('%b %d, %Y'),
            )
        return format_html(
            'Free — {}/{} used this month, {} remaining — resets {}',
            state.used,
            state.limit,
            state.remaining,
            state.resets_or_expires_at.strftime('%b %d, %Y'),
        )

    def grant_quota_view(self, request, object_id):
        tenant = get_object_or_404(Tenant, pk=object_id)
        has_active = tenant.quota_entitlements.filter(
            status=QuotaEntitlementStatus.ACTIVE,
        ).exists()

        if request.method == 'POST' and not has_active:
            form = GrantQuotaEntitlementForm(request.POST)
            if form.is_valid():
                try:
                    grant_entitlement(
                        tenant,
                        plan=form.cleaned_data['plan'],
                        purchased_limit=form.cleaned_data['purchased_limit'],
                        duration_months=form.cleaned_data['duration_months'],
                        granted_by=request.user,
                        notes=form.cleaned_data['notes'],
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(
                        request,
                        f'Granted {form.cleaned_data["plan"]} entitlement to {tenant.name}.',
                    )
                    return HttpResponseRedirect(
                        reverse('admin:accounts_tenant_change', args=[tenant.pk]),
                    )
        else:
            form = GrantQuotaEntitlementForm()

        return render(
            request,
            'admin/accounts/tenant/grant_quota.html',
            {
                **self.admin_site.each_context(request),
                'opts': self.model._meta,
                'tenant': tenant,
                'form': form,
                'has_active_entitlement': has_active,
                'title': f'Grant quota — {tenant.name}',
            },
        )

    def renew_quota_view(self, request, object_id):
        tenant = get_object_or_404(Tenant, pk=object_id)
        active_entitlement = tenant.quota_entitlements.filter(
            status=QuotaEntitlementStatus.ACTIVE,
        ).first()

        preview = None
        if request.method == 'POST':
            form = RenewQuotaEntitlementForm(request.POST)
            if form.is_valid():
                if '_preview' in request.POST:
                    preview = preview_renew_entitlement(
                        tenant,
                        plan=form.cleaned_data['plan'],
                        purchased_limit=form.cleaned_data['purchased_limit'],
                        duration_months=form.cleaned_data['duration_months'],
                    )
                else:
                    try:
                        renew_entitlement(
                            tenant,
                            plan=form.cleaned_data['plan'],
                            purchased_limit=form.cleaned_data['purchased_limit'],
                            duration_months=form.cleaned_data['duration_months'],
                            granted_by=request.user,
                            notes=form.cleaned_data['notes'],
                        )
                    except ValueError as exc:
                        messages.error(request, str(exc))
                    else:
                        messages.success(request, f'Renewed quota entitlement for {tenant.name}.')
                        return HttpResponseRedirect(
                            reverse('admin:accounts_tenant_change', args=[tenant.pk]),
                        )
        else:
            form = RenewQuotaEntitlementForm()
            preview = preview_renew_entitlement(
                tenant,
                plan=QuotaPlan.PRO_PLUS if tenant.quota_plan == QuotaPlan.PRO_PLUS else QuotaPlan.PRO,
                purchased_limit=20_000,
                duration_months=3,
            )

        return render(
            request,
            'admin/accounts/tenant/renew_quota.html',
            {
                **self.admin_site.each_context(request),
                'opts': self.model._meta,
                'tenant': tenant,
                'form': form,
                'active_entitlement': active_entitlement,
                'preview': preview,
                'title': f'Renew quota — {tenant.name}',
            },
        )

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

    @admin.action(description='Reactivate selected tenants')
    def reactivate_tenants(self, request, queryset):
        updated = queryset.filter(status=TenantStatus.SUSPENDED).update(status=TenantStatus.ACTIVE)
        self.message_user(request, f'Reactivated {updated} tenant(s).', messages.SUCCESS)

    @admin.action(description='Grant quota entitlement (wizard)')
    def grant_quota_action(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Select exactly one tenant to grant quota.', messages.ERROR)
            return
        tenant = queryset.first()
        return HttpResponseRedirect(reverse('admin:accounts_tenant_grant_quota', args=[tenant.pk]))

    @admin.action(description='Renew quota entitlement (wizard)')
    def renew_quota_action(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Select exactly one tenant to renew quota.', messages.ERROR)
            return
        tenant = queryset.first()
        return HttpResponseRedirect(reverse('admin:accounts_tenant_renew_quota', args=[tenant.pk]))


@admin.register(QuotaEntitlement)
class QuotaEntitlementAdmin(admin.ModelAdmin):
    list_display = (
        'tenant',
        'plan_at_grant',
        'quota_limit',
        'usage_count',
        'remaining_display',
        'carry_forward',
        'starts_at',
        'ends_at',
        'status',
    )
    list_filter = ('status', 'plan_at_grant')
    search_fields = ('tenant__name', 'tenant__slug', 'notes')
    readonly_fields = ('created_at', 'updated_at', 'remaining_display')
    raw_id_fields = ('tenant', 'renewed_from', 'granted_by')
    actions = ['cancel_entitlements', 'mark_expired']
    fieldsets = (
        (None, {
            'fields': (
                'tenant',
                'plan_at_grant',
                'status',
                'purchased_limit',
                'carry_forward',
                'quota_limit',
                'usage_count',
                'remaining_display',
                'starts_at',
                'ends_at',
                'renewed_from',
                'granted_by',
                'notes',
            ),
        }),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='Remaining')
    def remaining_display(self, obj):
        return obj.remaining

    def has_add_permission(self, request):
        return False

    def add_view(self, request, form_url='', extra_context=None):
        messages.info(
            request,
            'Create entitlements from Tenants → open a tenant → Grant quota (or use the list action).',
        )
        return HttpResponseRedirect(reverse('admin:accounts_tenant_changelist'))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_save_and_add_another'] = False
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.status == QuotaEntitlementStatus.ACTIVE:
            obj.tenant.quota_plan = obj.plan_at_grant
            obj.tenant.save(update_fields=['quota_plan', 'updated_at'])
        elif obj.status in {QuotaEntitlementStatus.EXPIRED, QuotaEntitlementStatus.CANCELLED}:
            has_active = obj.tenant.quota_entitlements.filter(
                status=QuotaEntitlementStatus.ACTIVE,
            ).exists()
            if not has_active and obj.tenant.quota_plan != QuotaPlan.FREE:
                obj.tenant.quota_plan = QuotaPlan.FREE
                obj.tenant.save(update_fields=['quota_plan', 'updated_at'])

    @admin.action(description='Cancel selected entitlements')
    def cancel_entitlements(self, request, queryset):
        updated = 0
        for entitlement in queryset.filter(status=QuotaEntitlementStatus.ACTIVE):
            entitlement.status = QuotaEntitlementStatus.CANCELLED
            entitlement.save(update_fields=['status', 'updated_at'])
            if not entitlement.tenant.quota_entitlements.filter(
                status=QuotaEntitlementStatus.ACTIVE,
            ).exists():
                entitlement.tenant.quota_plan = QuotaPlan.FREE
                entitlement.tenant.save(update_fields=['quota_plan', 'updated_at'])
            updated += 1
        self.message_user(request, f'Cancelled {updated} entitlement(s).', messages.WARNING)

    @admin.action(description='Mark selected as expired')
    def mark_expired(self, request, queryset):
        updated = 0
        for entitlement in queryset.filter(status=QuotaEntitlementStatus.ACTIVE):
            entitlement.status = QuotaEntitlementStatus.EXPIRED
            entitlement.save(update_fields=['status', 'updated_at'])
            if not entitlement.tenant.quota_entitlements.filter(
                status=QuotaEntitlementStatus.ACTIVE,
            ).exists():
                entitlement.tenant.quota_plan = QuotaPlan.FREE
                entitlement.tenant.save(update_fields=['quota_plan', 'updated_at'])
            updated += 1
        self.message_user(request, f'Marked {updated} entitlement(s) as expired.', messages.WARNING)


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'company_name', 'gstin', 'state', 'completed_at', 'updated_at')
    search_fields = ('company_name', 'gstin', 'tenant__name')
    readonly_fields = ('completed_at', 'created_at', 'updated_at')
    exclude = ('encrypted_nic_portal_password',)


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'tenant', 'role', 'is_primary', 'created_at')
    list_filter = ('role', 'is_primary')
    search_fields = ('user__email', 'tenant__name')
    raw_id_fields = ('user', 'tenant')


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'customer_label',
        'prefix',
        'tenant',
        'is_active_display',
        'created_at',
        'last_used_at',
        'revoked_at',
    )
    list_filter = ('revoked_at',)
    search_fields = ('name', 'customer_label', 'prefix', 'tenant__name')
    readonly_fields = ('prefix', 'key_hash', 'created_at', 'last_used_at')
    raw_id_fields = ('tenant',)
    actions = ['revoke_api_keys']

    @admin.display(boolean=True, description='Active')
    def is_active_display(self, obj):
        return obj.is_active

    @admin.action(description='Revoke selected API keys')
    def revoke_api_keys(self, request, queryset):
        revoked = 0
        for api_key in queryset.filter(revoked_at__isnull=True):
            revoke_api_key(api_key)
            revoked += 1
        self.message_user(request, f'Revoked {revoked} API key(s).', messages.SUCCESS)


@admin.register(StoredCertificate)
class StoredCertificateAdmin(admin.ModelAdmin):
    list_display = ('alias', 'tenant', 'created_at')
    search_fields = ('alias', 'tenant__name')
    raw_id_fields = ('tenant',)
    readonly_fields = ('created_at',)
    exclude = ('encrypted_pfx',)


@admin.register(TenantSignatureStyle)
class TenantSignatureStyleAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'name', 'is_default', 'is_enabled', 'anchor_text', 'updated_at')
    list_filter = ('is_enabled', 'is_default')
    search_fields = ('tenant__name', 'name', 'anchor_text')
    raw_id_fields = ('tenant',)


@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    list_display = (
        'tenant',
        'endpoint',
        'document_type',
        'success',
        'client_ip',
        'client_mac',
        'user_agent',
        'api_key',
        'user',
        'hash_before',
        'hash_after',
        'created_at',
    )
    list_filter = ('success', 'endpoint', 'document_type', 'detection_confidence')
    search_fields = ('hash_before', 'hash_after', 'client_ip', 'client_mac', 'user_agent', 'tenant__name')
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
        'client_mac',
        'user_agent',
        'api_key',
        'user',
        'created_at',
    )


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'used_at')
    readonly_fields = ('token', 'created_at')
    search_fields = ('user__email',)
    raw_id_fields = ('user',)


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'used_at')
    readonly_fields = ('token', 'created_at')
    search_fields = ('user__email',)
    raw_id_fields = ('user',)

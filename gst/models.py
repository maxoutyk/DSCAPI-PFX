from django.db import models

from accounts.models import APIKey, Tenant


class GstApiLog(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='gst_api_logs')
    endpoint = models.CharField(max_length=64)
    success = models.BooleanField(default=True)
    gstin = models.CharField(max_length=15, blank=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    api_key = models.ForeignKey(
        APIKey,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='gst_api_logs',
    )
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'GST API call'
        verbose_name_plural = 'GST API calls'

    def __str__(self):
        return f'{self.endpoint} ({self.tenant.name})'

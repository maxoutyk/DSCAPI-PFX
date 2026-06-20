from django import forms
from django.conf import settings

from signPdf.validation import PdfValidationError, validate_pdf_bytes

from .models import AgentDevice


class UsbSignForm(forms.Form):
    pdf_file = forms.FileField(label='PDF document')
    device_id = forms.ChoiceField(required=False, label='USB agent', choices=[])

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is None:
            self.fields.pop('device_id', None)
            return

        from datetime import timedelta

        from django.utils import timezone

        timeout = getattr(settings, 'USB_AGENT_HEARTBEAT_TIMEOUT_SECONDS', 90)
        cutoff = timezone.now() - timedelta(seconds=timeout)
        devices = list(
            tenant.agent_devices.filter(revoked_at__isnull=True, last_seen_at__gte=cutoff),
        )
        if len(devices) > 1:
            self.fields['device_id'].required = True
            self.fields['device_id'].choices = [
                (str(device.pk), device.label or device.prefix) for device in devices
            ]
        else:
            self.fields.pop('device_id', None)

    def clean_pdf_file(self):
        uploaded = self.cleaned_data.get('pdf_file')
        if not uploaded:
            return uploaded
        if uploaded.size > settings.PORTAL_SIGN_MAX_UPLOAD_BYTES:
            max_mb = settings.PORTAL_SIGN_MAX_UPLOAD_BYTES // (1024 * 1024)
            raise forms.ValidationError(f'PDF must be {max_mb} MB or smaller.')
        if not uploaded.name.lower().endswith('.pdf'):
            raise forms.ValidationError('Upload a PDF file.')
        uploaded.seek(0)
        try:
            validate_pdf_bytes(uploaded.read())
        except PdfValidationError as exc:
            raise forms.ValidationError(str(exc)) from exc
        finally:
            uploaded.seek(0)
        return uploaded

    def resolve_device(self) -> AgentDevice | None:
        if self.tenant is None:
            return None
        device_id = self.cleaned_data.get('device_id')
        if device_id:
            return AgentDevice.objects.filter(
                pk=int(device_id),
                tenant=self.tenant,
                revoked_at__isnull=True,
            ).first()
        from .services import resolve_portal_usb_device

        return resolve_portal_usb_device(self.tenant)

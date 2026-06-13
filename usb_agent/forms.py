from django import forms
from django.conf import settings

from signPdf.validation import PdfValidationError, validate_pdf_bytes


class UsbSignForm(forms.Form):
    pdf_file = forms.FileField(label='PDF document')

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

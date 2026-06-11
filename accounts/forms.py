from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm

from .models import TenantSignatureStyle
from .services import register_tenant, store_certificate


class RegistrationForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    organization_name = forms.CharField(max_length=200, label='Organization name')

    def save(self):
        return register_tenant(
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            organization_name=self.cleaned_data['organization_name'],
        )


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email')
    password = forms.CharField(widget=forms.PasswordInput)


class ResendVerificationForm(forms.Form):
    email = forms.EmailField(label='Email address')


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label='Email address')


class PasswordResetConfirmForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label='New password')
    password_confirm = forms.CharField(widget=forms.PasswordInput, min_length=8, label='Confirm new password')

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        password_confirm = cleaned.get('password_confirm')
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned


class APIKeyForm(forms.Form):
    name = forms.CharField(max_length=100, initial='Production')


class CertificateUploadForm(forms.Form):
    alias = forms.SlugField(max_length=80, help_text='Short name used in API calls (cert_alias).')
    pfx_file = forms.FileField()
    password = forms.CharField(
        widget=forms.PasswordInput,
        help_text='Used to validate the PFX now. Not stored — provide it on each sign request.',
    )

    def clean(self):
        cleaned = super().clean()
        pfx_file = cleaned.get('pfx_file')
        password = cleaned.get('password')
        if pfx_file and password:
            from signPdf.pdf_signing import load_pfx_credentials

            try:
                load_pfx_credentials(pfx_file.read(), password)
                pfx_file.seek(0)
            except ValueError as exc:
                raise forms.ValidationError(str(exc)) from exc
        return cleaned

    def save(self, tenant):
        return store_certificate(
            tenant,
            self.cleaned_data['alias'],
            self.cleaned_data['pfx_file'].read(),
        )


class SignatureStyleForm(forms.ModelForm):
    class Meta:
        model = TenantSignatureStyle
        fields = [
            'is_enabled',
            'anchor_text',
            'font_size',
            'box_min_width',
            'box_height',
            'box_right_padding',
            'box_shift_right',
            'box_gap_above_label',
            'box_shift_down_fitz',
            'box_page_margin',
            'icon_display_width',
            'icon_overlap_inset',
            'icon_padding',
            'custom_icon',
        ]
        widgets = {
            'is_enabled': forms.CheckboxInput,
            'anchor_text': forms.TextInput(attrs={'placeholder': 'Authorised Signatory'}),
        }
        help_texts = {
            'is_enabled': 'Enable only when you are ready to use custom placement. Until then, platform defaults apply.',
            'anchor_text': 'Exact text searched in the PDF to locate the signature box.',
            'box_shift_right': 'Positive moves the box right relative to the anchor label.',
            'box_gap_above_label': 'Gap between the anchor text and the bottom of the signature box.',
            'box_shift_down_fitz': 'Positive moves the signature box down (away from text above).',
        }

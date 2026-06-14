import base64
import binascii
import json

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from .models import Tenant, TenantSignatureStyle, TenantStatus
from .services import get_primary_tenant, register_tenant, store_certificate


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

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        if username and password:
            user = User.objects.filter(email__iexact=username.strip().lower()).first()
            if user and not user.is_active and user.check_password(password):
                tenant = get_primary_tenant(user)
                if tenant and tenant.status == TenantStatus.PENDING_EMAIL:
                    raise forms.ValidationError(
                        'Verify your email before signing in. '
                        'Check your inbox or use Resend verification below.',
                        code='pending_email',
                    )
        return super().clean()


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

    def clean_pfx_file(self):
        uploaded = self.cleaned_data.get('pfx_file')
        if not uploaded:
            return uploaded
        max_bytes = getattr(settings, 'PFX_MAX_UPLOAD_BYTES', 5 * 1024 * 1024)
        if uploaded.size > max_bytes:
            max_mb = max_bytes // (1024 * 1024)
            raise forms.ValidationError(f'PFX file must be {max_mb} MB or smaller.')
        return uploaded

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
            'name',
            'is_default',
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
            'is_default': forms.CheckboxInput,
            'name': forms.TextInput(attrs={'placeholder': 'Invoice style'}),
            'anchor_text': forms.TextInput(attrs={'placeholder': 'Authorised Signatory'}),
        }
        help_texts = {
            'name': 'Short label used in the portal and API (signature_style).',
            'is_default': 'Used when API calls omit signature_style.',
            'is_enabled': 'Disabled styles are ignored unless named explicitly in an API call.',
            'anchor_text': 'Exact text searched in the PDF to locate the signature box.',
            'box_shift_right': 'Positive moves the box right relative to the anchor label.',
            'box_gap_above_label': 'Gap between the anchor text and the bottom of the signature box.',
            'box_shift_down_fitz': 'Positive moves the signature box down (away from text above).',
        }

    def __init__(self, *args, tenant: Tenant | None = None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Enter a name for this style.')
        if self.tenant is None:
            return name
        qs = TenantSignatureStyle.objects.filter(tenant=self.tenant, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('A style with this name already exists.')
        return name


class PortalSignForm(forms.Form):
    pdf_file = forms.FileField(label='PDF document')
    cert_alias = forms.ChoiceField(label='Saved certificate')
    signature_style = forms.ChoiceField(
        required=False,
        label='Signature style',
        help_text='Optional. Uses your default enabled style when blank.',
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        label='PFX password',
        help_text='Not stored — required to unlock your certificate for signing.',
    )

    def __init__(self, *args, tenant: Tenant | None = None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        aliases = []
        style_choices = [('', 'Default enabled style')]
        if tenant is not None:
            aliases = list(tenant.certificates.values_list('alias', flat=True))
            style_choices.extend(
                (style.name, style.name + (' (default)' if style.is_default else ''))
                for style in tenant.signature_styles.filter(is_enabled=True).order_by('name')
            )
        self.fields['cert_alias'].choices = [(a, a) for a in aliases]
        self.fields['signature_style'].choices = style_choices

    def clean_signature_style(self):
        return (self.cleaned_data.get('signature_style') or '').strip()

    def clean_pdf_file(self):
        from signPdf.validation import PdfValidationError, validate_pdf_bytes

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

    def clean(self):
        cleaned = super().clean()
        if self.tenant and not self.tenant.certificates.exists():
            raise forms.ValidationError('Upload a saved certificate before signing in the portal.')
        return cleaned


class PublicSignForm(forms.Form):
    SIGNATURE_MODE_TEXT = 'text'
    SIGNATURE_MODE_IMAGE = 'image'

    pdf_file = forms.FileField(label='PDF document')
    signature_mode = forms.ChoiceField(
        choices=[
            (SIGNATURE_MODE_TEXT, 'Type your name'),
            (SIGNATURE_MODE_IMAGE, 'Upload signature image'),
        ],
        widget=forms.RadioSelect,
        initial=SIGNATURE_MODE_TEXT,
    )
    signer_name = forms.CharField(
        max_length=80,
        required=False,
        label='Your name',
    )
    signature_data = forms.CharField(widget=forms.HiddenInput, required=False)
    signature_image = forms.FileField(required=False, label='Signature image')
    placements_json = forms.CharField(widget=forms.HiddenInput, required=False)
    signature_width_ratio = forms.CharField(widget=forms.HiddenInput, required=False)

    def clean_pdf_file(self):
        uploaded = self.cleaned_data.get('pdf_file')
        if not uploaded:
            return uploaded
        if uploaded.size > settings.PORTAL_SIGN_MAX_UPLOAD_BYTES:
            max_mb = settings.PORTAL_SIGN_MAX_UPLOAD_BYTES // (1024 * 1024)
            raise forms.ValidationError(f'PDF must be {max_mb} MB or smaller.')
        if not uploaded.name.lower().endswith('.pdf'):
            raise forms.ValidationError('Upload a PDF file.')
        return uploaded

    def clean_signer_name(self):
        return (self.cleaned_data.get('signer_name') or '').strip()

    def clean_signature_width_ratio(self):
        from signPdf.visual_stamp import DEFAULT_SIGNATURE_WIDTH_PT

        raw = (self.cleaned_data.get('signature_width_ratio') or '').strip()
        if not raw:
            return DEFAULT_SIGNATURE_WIDTH_PT / 595.0
        try:
            ratio = float(raw)
        except (TypeError, ValueError) as exc:
            raise forms.ValidationError('Signature size is invalid.') from exc
        if not 0.08 <= ratio <= 0.45:
            raise forms.ValidationError('Signature size must be between 8% and 45% of page width.')
        return ratio

    def clean_placements_json(self):
        from signPdf.visual_stamp import MAX_PLACEMENTS, SignaturePlacement

        raw = (self.cleaned_data.get('placements_json') or '').strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError('Signature placements are invalid.') from exc
        if not isinstance(payload, list):
            raise forms.ValidationError('Signature placements must be a list.')
        if not payload:
            raise forms.ValidationError('Click on the preview to place at least one signature.')
        if len(payload) > MAX_PLACEMENTS:
            raise forms.ValidationError(f'You can sign at most {MAX_PLACEMENTS} pages at once.')

        placements: list[SignaturePlacement] = []
        seen_pages: set[int] = set()
        for item in payload:
            if not isinstance(item, dict):
                raise forms.ValidationError('Signature placement entry is invalid.')
            try:
                page_number = int(item.get('page'))
                pos_x = float(item.get('x'))
                pos_y = float(item.get('y'))
            except (TypeError, ValueError) as exc:
                raise forms.ValidationError('Signature placement entry is invalid.') from exc
            if page_number in seen_pages:
                raise forms.ValidationError(f'Page {page_number} was selected more than once.')
            seen_pages.add(page_number)
            placements.append(SignaturePlacement(page_number=page_number, pos_x=pos_x, pos_y=pos_y))
        return placements

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get('signature_mode')
        signer_name = cleaned.get('signer_name', '')
        signature_png = self._resolve_signature_png(cleaned)
        if signature_png is None:
            if mode == self.SIGNATURE_MODE_TEXT:
                raise forms.ValidationError('Enter your name to create a signature.')
            raise forms.ValidationError('Upload a signature image or draw your name.')
        if mode == self.SIGNATURE_MODE_TEXT and not signer_name:
            raise forms.ValidationError('Enter your name for the cursive signature.')
        cleaned['signature_png'] = signature_png
        cleaned['placements'] = cleaned.get('placements_json', [])
        cleaned['signature_width_ratio'] = cleaned.get('signature_width_ratio')
        return cleaned

    def _resolve_signature_png(self, cleaned: dict) -> bytes | None:
        from signPdf.visual_stamp import validate_signature_image

        raw_data = (cleaned.get('signature_data') or '').strip()
        if raw_data:
            if ',' in raw_data:
                raw_data = raw_data.split(',', 1)[1]
            try:
                image_bytes = base64.b64decode(raw_data, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise forms.ValidationError('Signature image data is invalid.') from exc
            try:
                png_bytes, _aspect = validate_signature_image(image_bytes)
            except Exception as exc:
                raise forms.ValidationError(str(exc)) from exc
            return png_bytes

        uploaded = cleaned.get('signature_image')
        if uploaded:
            image_bytes = uploaded.read()
            try:
                png_bytes, _aspect = validate_signature_image(image_bytes)
            except Exception as exc:
                raise forms.ValidationError(str(exc)) from exc
            return png_bytes
        return None

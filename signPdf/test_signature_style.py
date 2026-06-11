import fitz
from django.test import TestCase, override_settings

from accounts.models import Tenant, TenantSignatureStyle, TenantStatus
from signPdf.pdf_signing import find_text_in_pdf, signature_box_for_position
from signPdf.signature_style import SignatureStyleConfig, resolve_signature_style


def _pdf_with_anchor(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 500), text)
    data = doc.tobytes()
    doc.close()
    return data


class ResolveSignatureStyleTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Style Org',
            slug='style-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )

    def test_no_config_uses_platform_defaults(self):
        style = resolve_signature_style(self.tenant)
        self.assertFalse(style.is_custom)
        self.assertEqual(style.anchor_text, SignatureStyleConfig.from_settings().anchor_text)

    def test_disabled_config_uses_platform_defaults(self):
        TenantSignatureStyle.objects.create(
            tenant=self.tenant,
            is_enabled=False,
            anchor_text='Custom Signatory',
            box_shift_right=99,
        )
        style = resolve_signature_style(self.tenant)
        self.assertFalse(style.is_custom)
        self.assertEqual(style.box_shift_right, SignatureStyleConfig.from_settings().box_shift_right)

    def test_enabled_config_overrides_fields(self):
        TenantSignatureStyle.objects.create(
            tenant=self.tenant,
            is_enabled=True,
            anchor_text='Authorized Signatory',
            box_shift_right=42,
            box_gap_above_label=10,
        )
        style = resolve_signature_style(self.tenant)
        self.assertTrue(style.is_custom)
        self.assertEqual(style.anchor_text, 'Authorized Signatory')
        self.assertEqual(style.box_shift_right, 42)
        self.assertEqual(style.box_gap_above_label, 10)
        self.assertEqual(style.font_size, SignatureStyleConfig.from_settings().font_size)

    @override_settings(SIGNATURE_ANCHOR_TEXT='Authorised Signatory')
    def test_find_text_uses_custom_anchor_when_enabled(self):
        TenantSignatureStyle.objects.create(
            tenant=self.tenant,
            is_enabled=True,
            anchor_text='For Company',
        )
        style = resolve_signature_style(self.tenant)
        default_positions = find_text_in_pdf(_pdf_with_anchor('Authorised Signatory'), style=style)
        custom_positions = find_text_in_pdf(_pdf_with_anchor('For Company'), style=style)
        self.assertEqual(len(default_positions), 0)
        self.assertEqual(len(custom_positions), 1)

    def test_signature_box_uses_custom_offsets(self):
        position = {
            'x0': 100,
            'y0': 500,
            'x1': 220,
            'y1': 512,
            'page_width': 595,
            'page_height': 842,
        }
        default_style = SignatureStyleConfig.from_settings()
        default_box = signature_box_for_position(position, style=default_style)
        TenantSignatureStyle.objects.create(
            tenant=self.tenant,
            is_enabled=True,
            box_shift_right=50,
        )
        custom_box = signature_box_for_position(position, style=resolve_signature_style(self.tenant))
        self.assertGreater(custom_box[2], default_box[2])

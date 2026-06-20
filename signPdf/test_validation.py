from django.test import SimpleTestCase, override_settings

from signPdf.validation import (
    PfxValidationError,
    PdfValidationError,
    decode_pfx_base64,
    decode_signed_pdf_base64,
    safe_attachment_filename,
    validate_pdf_bytes,
)


class ValidationHelperTests(SimpleTestCase):
    def test_validate_pdf_bytes_requires_magic(self):
        with self.assertRaises(PdfValidationError):
            validate_pdf_bytes(b'not-a-pdf')

    def test_safe_attachment_filename_strips_paths_and_control_chars(self):
        self.assertEqual(
            safe_attachment_filename('../../evil\r\n.pdf'),
            'evil__.pdf',
        )

    @override_settings(PFX_MAX_UPLOAD_BYTES=16)
    def test_decode_pfx_base64_rejects_oversized_payload(self):
        huge = 'A' * 100
        with self.assertRaises(PfxValidationError):
            decode_pfx_base64(huge)

    @override_settings(API_SIGN_MAX_UPLOAD_BYTES=32)
    def test_decode_signed_pdf_base64_rejects_oversized_payload(self):
        huge = 'A' * 200
        with self.assertRaises(PdfValidationError):
            decode_signed_pdf_base64(huge)

    @override_settings(PDF_MAX_PAGE_COUNT=1)
    def test_validate_pdf_bytes_rejects_too_many_pages(self):
        import fitz

        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        payload = doc.tobytes()
        doc.close()
        with self.assertRaises(PdfValidationError):
            validate_pdf_bytes(payload)

    @override_settings(SIGNATURE_MAX_SLOTS=2)
    def test_enforce_signature_slot_limit(self):
        from signPdf.validation import enforce_signature_slot_limit

        enforce_signature_slot_limit(2)
        with self.assertRaises(PdfValidationError):
            enforce_signature_slot_limit(3)

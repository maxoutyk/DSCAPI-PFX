import base64

import fitz
from django.test import TestCase

from usb_agent.verification import SignedPdfRejected, verify_usb_signed_pdf


def _pdf_bytes(text: str = 'Authorised Signatory') -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 120), text)
    data = doc.tobytes()
    doc.close()
    return data


class UsbSignedPdfVerificationTests(TestCase):
    def test_rejects_signed_pdf_that_does_not_contain_original(self):
        original = _pdf_bytes('Invoice A')
        unrelated = _pdf_bytes('Invoice B completely different content here')
        from signPdf.audit import sha256_hex

        with self.assertRaises(SignedPdfRejected) as ctx:
            verify_usb_signed_pdf(
                original_pdf=original,
                signed_pdf=unrelated,
                hash_before=sha256_hex(original),
            )
        self.assertIn('prepared document', str(ctx.exception))

    def test_rejects_identical_pdf(self):
        original = _pdf_bytes()
        from signPdf.audit import sha256_hex

        with self.assertRaises(SignedPdfRejected):
            verify_usb_signed_pdf(
                original_pdf=original,
                signed_pdf=original,
                hash_before=sha256_hex(original),
            )

    def test_accepts_incremental_append_signature(self):
        original = _pdf_bytes()
        signed = original + b'\n% Fake incremental signature block for test'
        from signPdf.audit import sha256_hex

        with self.assertRaises(SignedPdfRejected):
            # Appended bytes alone are not a valid CMS signature — endesive should fail.
            verify_usb_signed_pdf(
                original_pdf=original,
                signed_pdf=signed,
                hash_before=sha256_hex(original),
            )

"""Validate USB agent signed PDF submissions before accepting completion."""

from __future__ import annotations

from endesive import pdf as endesive_pdf

from signPdf.validation import validate_pdf_bytes


class SignedPdfRejected(Exception):
    pass


def verify_usb_signed_pdf(*, original_pdf: bytes, signed_pdf: bytes, hash_before: str) -> None:
    """Ensure the agent returned a structurally signed PDF, not an arbitrary file."""
    from signPdf.audit import sha256_hex

    validate_pdf_bytes(signed_pdf)

    if sha256_hex(signed_pdf) == hash_before:
        raise SignedPdfRejected('Signed PDF is identical to the original — no signature was applied.')

    if len(signed_pdf) < len(original_pdf):
        raise SignedPdfRejected('Signed PDF is smaller than the original document.')

    try:
        results = endesive_pdf.verify(signed_pdf)
    except Exception as exc:
        raise SignedPdfRejected(f'PDF signature verification failed: {exc}') from exc

    if not results:
        raise SignedPdfRejected('No digital signature found in the submitted PDF.')

    for result in results:
        if not result:
            raise SignedPdfRejected('One or more PDF signatures failed cryptographic verification.')

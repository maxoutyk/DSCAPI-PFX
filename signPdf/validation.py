"""Shared validation for PDF signing API and portal uploads."""

from __future__ import annotations

import base64
import binascii
import re

import fitz
from django.conf import settings


class PdfValidationError(ValueError):
    pass


def max_pdf_page_count() -> int:
    return int(getattr(settings, 'PDF_MAX_PAGE_COUNT', 200))


def max_signature_slots() -> int:
    return int(getattr(settings, 'SIGNATURE_MAX_SLOTS', 20))


GENERIC_SIGNING_FAILURE_MESSAGE = 'Failed to sign PDF. Check the document and certificate, then try again.'


class PfxValidationError(ValueError):
    pass


def max_api_upload_bytes() -> int:
    return int(getattr(settings, 'API_SIGN_MAX_UPLOAD_BYTES', settings.PORTAL_SIGN_MAX_UPLOAD_BYTES))


def max_pfx_upload_bytes() -> int:
    return int(getattr(settings, 'PFX_MAX_UPLOAD_BYTES', 5 * 1024 * 1024))


def _max_base64_length(max_bytes: int) -> int:
    return (max_bytes * 4) // 3 + 4


def safe_attachment_filename(name: str, *, default: str = 'document.pdf') -> str:
    """Strip path segments and control characters from user-supplied download names."""
    base = (name or default).strip().replace('\\', '/').split('/')[-1]
    cleaned = re.sub(r'[^\w.\- ]', '_', base).strip('._ ')[:200]
    return cleaned or default


def decode_pdf_base64(value: str, *, max_bytes: int | None = None) -> bytes:
    max_bytes = max_bytes or max_api_upload_bytes()
    raw = (value or '').strip()
    if not raw:
        raise PdfValidationError('pdf_base64 is required.')
    if len(raw) > _max_base64_length(max_bytes):
        raise PdfValidationError(
            f'PDF exceeds maximum size of {max_bytes // (1024 * 1024)} MB.',
        )
    try:
        pdf_data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PdfValidationError(f'Failed to decode base64 PDF data: {exc}') from exc
    if len(pdf_data) > max_bytes:
        raise PdfValidationError(
            f'PDF exceeds maximum size of {max_bytes // (1024 * 1024)} MB.',
        )
    validate_pdf_bytes(pdf_data)
    return pdf_data


def validate_pdf_bytes(pdf_data: bytes) -> None:
    if not pdf_data:
        raise PdfValidationError('PDF data is empty.')
    if not pdf_data.startswith(b'%PDF'):
        raise PdfValidationError('File is not a valid PDF.')
    try:
        doc = fitz.open(stream=pdf_data, filetype='pdf')
        page_count = len(doc)
        doc.close()
    except Exception as exc:
        raise PdfValidationError('PDF could not be opened.') from exc
    if page_count == 0:
        raise PdfValidationError('PDF has no pages.')
    max_pages = max_pdf_page_count()
    if page_count > max_pages:
        raise PdfValidationError(f'PDF exceeds the maximum of {max_pages} pages.')


def enforce_signature_slot_limit(position_count: int) -> None:
    limit = max_signature_slots()
    if position_count > limit:
        raise PdfValidationError(
            f'Too many signature positions ({position_count}). Maximum is {limit}.',
        )


def decode_pfx_base64(value: str, *, max_bytes: int | None = None) -> bytes:
    max_bytes = max_bytes or max_pfx_upload_bytes()
    raw = (value or '').strip()
    if not raw:
        raise PfxValidationError('pfx_base64 is required.')
    if len(raw) > _max_base64_length(max_bytes):
        raise PfxValidationError(
            f'PFX exceeds maximum size of {max_bytes // (1024 * 1024)} MB.',
        )
    try:
        pfx_data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PfxValidationError(f'Failed to decode base64 PFX data: {exc}') from exc
    if len(pfx_data) > max_bytes:
        raise PfxValidationError(
            f'PFX exceeds maximum size of {max_bytes // (1024 * 1024)} MB.',
        )
    return pfx_data


def decode_signed_pdf_base64(value: str, *, max_bytes: int | None = None) -> bytes:
    """Decode agent-submitted signed PDFs with the same caps as API uploads."""
    return decode_pdf_base64(value, max_bytes=max_bytes or max_api_upload_bytes())

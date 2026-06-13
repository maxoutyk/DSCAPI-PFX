"""Shared validation for PDF signing API and portal uploads."""

from __future__ import annotations

import base64
import binascii

from django.conf import settings


class PdfValidationError(ValueError):
    pass


def max_api_upload_bytes() -> int:
    return int(getattr(settings, 'API_SIGN_MAX_UPLOAD_BYTES', settings.PORTAL_SIGN_MAX_UPLOAD_BYTES))


def _max_base64_length(max_bytes: int) -> int:
    return (max_bytes * 4) // 3 + 4


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

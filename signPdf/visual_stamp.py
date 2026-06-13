"""Visual PDF stamping (name/image overlay) — not cryptographic signing."""

from __future__ import annotations

import io
from dataclasses import dataclass

import fitz
from PIL import Image

from .validation import PdfValidationError, validate_pdf_bytes


class VisualStampError(ValueError):
    pass


MAX_SIGNATURE_IMAGE_BYTES = 2 * 1024 * 1024
MAX_SIGNATURE_WIDTH_PX = 1200
MAX_SIGNATURE_HEIGHT_PX = 600
MAX_PLACEMENTS = 50
DEFAULT_SIGNATURE_WIDTH_PT = 160.0


@dataclass(frozen=True)
class SignaturePlacement:
    page_number: int
    pos_x: float
    pos_y: float


def validate_signature_image(image_data: bytes) -> tuple[bytes, float]:
    """Return PNG bytes and width/height aspect ratio."""
    if not image_data:
        raise VisualStampError('Signature image is required.')
    if len(image_data) > MAX_SIGNATURE_IMAGE_BYTES:
        raise VisualStampError('Signature image is too large (max 2 MB).')
    try:
        image = Image.open(io.BytesIO(image_data))
        image.load()
    except Exception as exc:
        raise VisualStampError('Signature image is not a valid PNG or JPEG file.') from exc
    if image.width > MAX_SIGNATURE_WIDTH_PX or image.height > MAX_SIGNATURE_HEIGHT_PX:
        raise VisualStampError('Signature image dimensions are too large.')
    if image.width < 8 or image.height < 8:
        raise VisualStampError('Signature image is too small.')

    buffer = io.BytesIO()
    if image.mode not in ('RGB', 'RGBA'):
        image = image.convert('RGBA')
    image.save(buffer, format='PNG')
    png_data = buffer.getvalue()
    aspect = image.width / image.height
    return png_data, aspect


def stamp_pdf_with_signature(
    pdf_data: bytes,
    *,
    signature_png: bytes,
    page_number: int,
    pos_x: float,
    pos_y: float,
    signature_width_pt: float = DEFAULT_SIGNATURE_WIDTH_PT,
) -> bytes:
    return stamp_pdf_with_signatures(
        pdf_data,
        signature_png=signature_png,
        placements=[SignaturePlacement(page_number=page_number, pos_x=pos_x, pos_y=pos_y)],
        signature_width_pt=signature_width_pt,
    )


def _resolve_signature_width_pt(
    page_rect: fitz.Rect,
    *,
    signature_width_pt: float,
    signature_width_ratio: float | None,
) -> float:
    if signature_width_ratio is not None:
        width = page_rect.width * signature_width_ratio
    else:
        width = signature_width_pt
    return min(width, page_rect.width * 0.45)


def stamp_pdf_with_signatures(
    pdf_data: bytes,
    *,
    signature_png: bytes,
    placements: list[SignaturePlacement],
    signature_width_pt: float = DEFAULT_SIGNATURE_WIDTH_PT,
    signature_width_ratio: float | None = None,
) -> bytes:
    """Place the same signature image on one or more PDF pages."""
    validate_pdf_bytes(pdf_data)
    if not placements:
        raise VisualStampError('At least one signature placement is required.')
    if len(placements) > MAX_PLACEMENTS:
        raise VisualStampError(f'You can sign at most {MAX_PLACEMENTS} pages at once.')

    signature_png, aspect = validate_signature_image(signature_png)
    seen_pages: set[int] = set()

    doc = fitz.open(stream=pdf_data, filetype='pdf')
    try:
        for placement in placements:
            page_number = placement.page_number
            pos_x = placement.pos_x
            pos_y = placement.pos_y

            if page_number < 1:
                raise VisualStampError('Page number must be at least 1.')
            if page_number > doc.page_count:
                raise VisualStampError(f'Page {page_number} does not exist in this PDF.')
            if not 0 <= pos_x <= 1 or not 0 <= pos_y <= 1:
                raise VisualStampError('Signature position is out of range.')
            if page_number in seen_pages:
                raise VisualStampError(f'Page {page_number} has more than one signature placement.')
            seen_pages.add(page_number)

            page = doc[page_number - 1]
            page_rect = page.rect
            sig_width = _resolve_signature_width_pt(
                page_rect,
                signature_width_pt=signature_width_pt,
                signature_width_ratio=signature_width_ratio,
            )
            sig_height = sig_width / aspect

            center_x = pos_x * page_rect.width
            center_y = pos_y * page_rect.height
            left = center_x - (sig_width / 2)
            top = center_y - (sig_height / 2)

            left = max(0, min(left, page_rect.width - sig_width))
            top = max(0, min(top, page_rect.height - sig_height))
            rect = fitz.Rect(left, top, left + sig_width, top + sig_height)
            page.insert_image(rect, stream=signature_png, keep_proportion=True)

        return doc.tobytes(deflate=True, garbage=3)
    finally:
        doc.close()
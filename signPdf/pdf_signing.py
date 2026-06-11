import datetime
import os
from pathlib import Path

import fitz
from PIL import Image
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs12
from django.conf import settings

from .signature_style import DEFAULT_ANCHOR_TEXT, SignatureStyleConfig, resolve_signature_style

SIGNATURE_ANCHOR_TEXT = DEFAULT_ANCHOR_TEXT


def find_text_in_pdf(pdf_data, text=None, *, style: SignatureStyleConfig | None = None):
    anchor = text
    if anchor is None:
        anchor = style.anchor_text if style else getattr(settings, 'SIGNATURE_ANCHOR_TEXT', SIGNATURE_ANCHOR_TEXT)

    text_positions = []
    try:
        doc = fitz.open(stream=pdf_data, filetype="pdf")
    except Exception:
        return []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text_instances = page.search_for(anchor)
        page_size = page.rect

        for text_instance in text_instances:
            text_positions.append({
                'page_number': page_num,
                'x0': text_instance.x0,
                'y0': text_instance.y0,
                'x1': text_instance.x1,
                'y1': text_instance.y1,
                'page_width': page_size.width,
                'page_height': page_size.height,
            })

    return text_positions


def get_indian_time_str():
    current_utc_time = datetime.datetime.now(datetime.timezone.utc)
    indian_time = current_utc_time + datetime.timedelta(hours=5, minutes=30)
    return indian_time.strftime('%Y-%m-%d %H:%M:%S') + ' UTC+5:30', indian_time


def get_cn_from_certificate(certificate):
    for attr in certificate.subject:
        if attr.oid == x509.NameOID.COMMON_NAME:
            return attr.value
    return 'Unknown'


def read_pfx_file(pfx_path):
    if not pfx_path or pfx_path.strip() != pfx_path:
        raise ValueError('pfx_path must be a non-empty relative path')

    if os.path.isabs(pfx_path):
        raise ValueError('pfx_path must be relative to the certs directory')

    normalized = os.path.normpath(pfx_path)
    if normalized.startswith('..') or normalized in ('.', ''):
        raise ValueError('Invalid pfx_path')

    certs_dir = Path(getattr(settings, 'PFX_CERTS_DIR', Path(settings.BASE_DIR) / 'certs')).resolve()
    full_path = (certs_dir / normalized).resolve()

    if certs_dir not in full_path.parents and full_path != certs_dir:
        raise ValueError('Invalid pfx_path')

    if not full_path.is_file():
        raise ValueError(f'PFX file not found: {pfx_path}')

    return full_path.read_bytes()


def load_pfx_credentials(pfx_data, password):
    try:
        password_bytes = password.encode('utf-8') if password else None
        private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
            pfx_data,
            password_bytes,
            default_backend(),
        )
    except ValueError as exc:
        raise ValueError('Failed to load PFX: invalid password or corrupt file') from exc

    if private_key is None or certificate is None:
        raise ValueError('PFX file does not contain a private key and certificate')

    return private_key, certificate, list(additional_certs or [])


def format_contact_text(cn, indian_time_str):
    if ' ' in indian_time_str:
        date_str, time_str = indian_time_str.split(' ', 1)
        return f'Digitally signed by \n{cn}\nDate: {date_str}\n{time_str}'
    return f'Digitally signed by \n{cn}\nDate: {indian_time_str}'


def build_signing_dict(cn, indian_time_str, indian_time, *, style: SignatureStyleConfig | None = None):
    style = style or resolve_signature_style()
    date = indian_time - datetime.timedelta(hours=11)
    date = date.strftime('%Y%m%d%H%M%S+00\'00\'')

    dct = {
        "sigflags": 3,
        "sigbutton": True,
        "contact": format_contact_text(cn, indian_time_str),
        "location": 'India',
        "signingdate": date.encode(),
        "reason": 'Approved',
        "text": {
            'wraptext': True,
            'fontsize': style.font_size,
            'textalign': 'left',
            'linespacing': 1,
        },
    }

    return dct


def apply_overlapping_signature_layout(position_dct, signaturebox, *, style: SignatureStyleConfig | None = None):
    """Draw tick behind signature text (overlapping), not side-by-side."""
    style = style or resolve_signature_style()
    x_left, y_bottom, x_right, y_top = signaturebox
    width = x_right - x_left
    height = y_top - y_bottom
    font_size = position_dct.get('text', {}).get('fontsize', 6)
    contact = position_dct['contact']
    line_spacing = position_dct.get('text', {}).get('linespacing', 1.0)

    position_dct.pop('signature_appearance', None)

    icon_path = style.icon_path
    if not icon_path or not os.path.isfile(icon_path):
        position_dct['signature'] = contact
        return

    icon_w = style.icon_display_width

    with Image.open(icon_path) as tick_image:
        tick_w, tick_h = tick_image.size
        bbox = tick_image.getbbox()
        if bbox:
            tick_w = bbox[2] - bbox[0]
            tick_h = bbox[3] - bbox[1]

    icon_h = min(height - 4, int(icon_w * tick_h / tick_w))
    icon_pad = style.icon_padding
    overlap_inset = style.icon_overlap_inset

    box_x1, box_y1 = 0, 2
    box_x2, box_y2 = width, height - 2
    icon_y1 = box_y1 + ((box_y2 - box_y1) - icon_h) / 2
    icon_x2 = box_x2 - icon_pad - overlap_inset
    icon_x1 = max(box_x1 + icon_pad, icon_x2 - icon_w)

    position_dct['manual_images'] = {'Tick': icon_path}
    position_dct['signature_manual'] = [
        ['image', 'Tick', icon_x1, icon_y1, icon_x1 + icon_w, icon_y1 + icon_h, False, True],
        ['fill_colour', 0, 0, 0],
        [
            'text_box', contact, 'default',
            box_x1, box_y1, box_x2 - box_x1, box_y2 - box_y1,
            font_size, True, 'left', 'middle', line_spacing,
        ],
    ]


def signature_box_for_position(position, *, style: SignatureStyleConfig | None = None):
    style = style or resolve_signature_style()

    page_width = position['page_width']
    text_width = position['x1'] - position['x0']
    box_width = max(text_width + 20, style.box_min_width)

    x_right = min(
        page_width - style.box_page_margin,
        position['x1'] + style.box_right_padding + style.box_shift_right,
    )
    x_left = max(style.box_page_margin, x_right - box_width)

    # Anchor relative to the matched label (fitz y grows downward).
    fitz_box_bottom = position['y0'] - style.box_gap_above_label + style.box_shift_down_fitz
    fitz_box_top = fitz_box_bottom - style.box_height
    y_bottom = position['page_height'] - fitz_box_bottom
    y_top = position['page_height'] - fitz_box_top

    return (
        x_left,
        y_bottom,
        x_right,
        y_top,
    )


def sign_pdf_at_positions(pdf_data, text_positions, dct, sign_fn, *, style: SignatureStyleConfig | None = None):
    """
    Apply one or more signatures. endesive returns incremental PDF bytes per call;
    those must be appended to the document built so far before the next sign.
    """
    style = style or resolve_signature_style()
    signed_pdf_data = pdf_data
    for index, position in enumerate(text_positions):
        position_dct = dct.copy()
        position_dct["sigpage"] = position['page_number']
        position_dct['sigfield'] = f"Signature{index + 1}"
        position_dct['auto_sigfield'] = True
        signaturebox = signature_box_for_position(position, style=style)
        position_dct["signaturebox"] = signaturebox
        apply_overlapping_signature_layout(position_dct, signaturebox, style=style)
        increment = sign_fn(signed_pdf_data, position_dct)
        signed_pdf_data = signed_pdf_data + increment
    return signed_pdf_data

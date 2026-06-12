"""PDF signing helpers for the desktop agent (PKCS#11 USB token + PFX dev fallback)."""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path


class Pkcs11NotAvailable(Exception):
    """Raised when no PKCS#11 driver or USB token is available."""


def _ensure_django():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agent_settings')
    if getattr(sys, 'frozen', False):
        agent_dir = Path(sys._MEIPASS)
        if str(agent_dir) not in sys.path:
            sys.path.insert(0, str(agent_dir))
    else:
        repo_root = Path(__file__).resolve().parents[1]
        agent_dir = Path(__file__).resolve().parent
        for path in (str(repo_root), str(agent_dir)):
            if path not in sys.path:
                sys.path.insert(0, path)
    import django

    django.setup()


def _style_from_placement(placement: dict):
    from signPdf.signature_style import SignatureStyleConfig

    style_data = placement.get('style', {})
    base_style = SignatureStyleConfig.from_settings()
    return replace(
        base_style,
        anchor_text=style_data.get('anchor_text', base_style.anchor_text),
        font_size=style_data.get('font_size', base_style.font_size),
        box_min_width=style_data.get('box_min_width', base_style.box_min_width),
        box_height=style_data.get('box_height', base_style.box_height),
        box_right_padding=style_data.get('box_right_padding', base_style.box_right_padding),
        box_shift_right=style_data.get('box_shift_right', base_style.box_shift_right),
        box_gap_above_label=style_data.get('box_gap_above_label', base_style.box_gap_above_label),
        box_shift_down_fitz=style_data.get('box_shift_down_fitz', base_style.box_shift_down_fitz),
        box_page_margin=style_data.get('box_page_margin', base_style.box_page_margin),
        icon_display_width=style_data.get('icon_display_width', base_style.icon_display_width),
        icon_overlap_inset=style_data.get('icon_overlap_inset', base_style.icon_overlap_inset),
        icon_padding=style_data.get('icon_padding', base_style.icon_padding),
        is_custom=style_data.get('is_custom', False),
    )


def sign_pdf_with_pkcs11(pdf_data: bytes, placement: dict) -> bytes:
    from pkcs11_signing import TokenSigner, resolve_pkcs11_dll

    dll_path = resolve_pkcs11_dll()
    if not dll_path:
        raise Pkcs11NotAvailable(
            'No PKCS#11 driver found. Install your DSC token software or set IG_AGENT_PKCS11_DLL.',
        )

    _ensure_django()
    from endesive import pdf as endesive_pdf
    from signPdf.pdf_signing import build_signing_dict, get_cn_from_certificate, get_indian_time_str, sign_pdf_at_positions
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend

    signer = TokenSigner(dll_path)
    try:
        _key_id, cert_der = signer.certificate()
        certificate = x509.load_der_x509_certificate(cert_der, default_backend())
        style = _style_from_placement(placement)
        positions = placement['positions']
        indian_time_str, indian_time = get_indian_time_str()
        cn = get_cn_from_certificate(certificate)
        dct = build_signing_dict(cn, indian_time_str, indian_time, style=style)
        return sign_pdf_at_positions(
            pdf_data,
            positions,
            dct,
            lambda data, position_dct: endesive_pdf.cms.sign(
                data, position_dct, None, None, [], 'sha256', signer,
            ),
            style=style,
        )
    finally:
        signer.logout()


def sign_pdf_with_pfx(pdf_data: bytes, placement: dict, pfx_path: str, password: str) -> bytes:
    _ensure_django()
    from endesive import pdf as endesive_pdf
    from signPdf.pdf_signing import (
        build_signing_dict,
        get_cn_from_certificate,
        get_indian_time_str,
        load_pfx_credentials,
        sign_pdf_at_positions,
    )

    pfx_bytes = Path(pfx_path).read_bytes()
    private_key, certificate, additional_certs = load_pfx_credentials(pfx_bytes, password)
    style = _style_from_placement(placement)
    positions = placement['positions']
    indian_time_str, indian_time = get_indian_time_str()
    cn = get_cn_from_certificate(certificate)
    dct = build_signing_dict(cn, indian_time_str, indian_time, style=style)
    return sign_pdf_at_positions(
        pdf_data,
        positions,
        dct,
        lambda data, position_dct: endesive_pdf.cms.sign(
            data, position_dct, private_key, certificate, additional_certs, 'sha256',
        ),
        style=style,
    )

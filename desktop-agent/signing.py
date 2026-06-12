"""PDF signing helpers for the desktop agent (PFX dev / future PKCS#11)."""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path


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
    from signPdf.signature_style import SignatureStyleConfig

    pfx_bytes = Path(pfx_path).read_bytes()
    private_key, certificate, additional_certs = load_pfx_credentials(pfx_bytes, password)
    style_data = placement.get('style', {})
    base_style = SignatureStyleConfig.from_settings()
    style = replace(
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

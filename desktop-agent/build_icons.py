#!/usr/bin/env python3
"""Regenerate agent_icon.ico/png and copy portal logo for the desktop agent UI."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
LOGO_HEADER_SRC = REPO / 'accounts' / 'static' / 'accounts' / 'img' / 'ig-logo-light.png'
LOGO_ICON_SRC = REPO / 'accounts' / 'static' / 'accounts' / 'img' / 'ig-logo-dark.png'
ASSETS = ROOT / 'assets'
OUT_PNG = ASSETS / 'agent_icon.png'
OUT_ICO = ASSETS / 'agent_icon.ico'
OUT_LOGO = ASSETS / 'ig-logo-light.png'

NAVY = (2, 6, 38, 255)
ORANGE = (255, 102, 0, 255)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _crop_to_content(image: Image.Image) -> Image.Image:
    bbox = image.getbbox()
    if not bbox:
        return image
    return image.crop(bbox)


def _square_icon(master_size: int = 512) -> Image.Image:
    """High-contrast app icon: IG orange tile with white brand mark (readable in taskbar)."""
    canvas = Image.new('RGBA', (master_size, master_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    margin = int(master_size * 0.08)
    draw.rounded_rectangle(
        (margin, margin, master_size - margin, master_size - margin),
        radius=int(master_size * 0.18),
        fill=ORANGE,
    )

    if LOGO_ICON_SRC.is_file():
        logo = _crop_to_content(Image.open(LOGO_ICON_SRC).convert('RGBA'))
        target_w = int(master_size * 0.62)
        ratio = target_w / logo.width
        target_h = max(1, int(logo.height * ratio))
        logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
        x = (master_size - target_w) // 2
        y = (master_size - target_h) // 2
        canvas.paste(logo, (x, y), logo)
        return canvas

    font_size = int(master_size * 0.34)
    try:
        font = ImageFont.truetype('segoeuib.ttf', font_size)
    except OSError:
        font = ImageFont.load_default()
    draw.text((master_size * 0.28, master_size * 0.28), 'IG', fill=(255, 255, 255, 255), font=font)
    return canvas


def main() -> None:
    if not LOGO_HEADER_SRC.is_file():
        raise SystemExit(f'Missing portal logo: {LOGO_HEADER_SRC}')

    ASSETS.mkdir(parents=True, exist_ok=True)
    master = _square_icon(512)
    master.save(OUT_PNG)

    layers = [master.resize((size, size), Image.Resampling.LANCZOS) for size in ICO_SIZES]
    layers[-1].save(
        OUT_ICO,
        format='ICO',
        sizes=[(layer.width, layer.height) for layer in layers],
        append_images=layers[:-1],
    )

    header = _crop_to_content(Image.open(LOGO_HEADER_SRC).convert('RGBA'))
    header.save(OUT_LOGO)
    print(f'Wrote {OUT_PNG.name}, {OUT_ICO.name}, {OUT_LOGO.name}')


if __name__ == '__main__':
    main()

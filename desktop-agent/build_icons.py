#!/usr/bin/env python3
"""Regenerate agent_icon.ico/png and copy portal logo for the desktop agent UI."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
LOGO_SRC = REPO / 'accounts' / 'static' / 'accounts' / 'img' / 'ig-logo-light.png'
ASSETS = ROOT / 'assets'
OUT_PNG = ASSETS / 'agent_icon.png'
OUT_ICO = ASSETS / 'agent_icon.ico'
OUT_LOGO = ASSETS / 'ig-logo-light.png'

NAVY = (2, 6, 38, 255)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _square_icon(master_size: int = 512) -> Image.Image:
    logo = Image.open(LOGO_SRC).convert('RGBA')
    canvas = Image.new('RGBA', (master_size, master_size), NAVY)
    target_w = int(master_size * 0.74)
    ratio = target_w / logo.width
    target_h = max(1, int(logo.height * ratio))
    logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
    x = (master_size - target_w) // 2
    y = (master_size - target_h) // 2
    canvas.paste(logo, (x, y), logo)
    return canvas


def main() -> None:
    if not LOGO_SRC.is_file():
        raise SystemExit(f'Missing portal logo: {LOGO_SRC}')

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

    logo = Image.open(LOGO_SRC).convert('RGBA')
    logo.save(OUT_LOGO)
    print(f'Wrote {OUT_PNG.name}, {OUT_ICO.name}, {OUT_LOGO.name}')


if __name__ == '__main__':
    main()

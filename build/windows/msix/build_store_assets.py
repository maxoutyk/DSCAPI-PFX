#!/usr/bin/env python3
"""Generate Microsoft Store logo assets for the IG E-Sign Agent MSIX package."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

STORE_SIZES = {
    'StoreLogo.png': (50, 50),
    'Square44x44Logo.png': (44, 44),
    'Square150x150Logo.png': (150, 150),
    'Wide310x150Logo.png': (310, 150),
}


def _crop_to_content(image: Image.Image) -> Image.Image:
    bbox = image.getbbox()
    if not bbox:
        return image
    return image.crop(bbox)


def _square_icon(source: Path, master_size: int = 512) -> Image.Image:
    logo = _crop_to_content(Image.open(source).convert('RGBA'))
    canvas = Image.new('RGBA', (master_size, master_size), (255, 255, 255, 255))
    padding = int(master_size * 0.06)
    inner = master_size - (padding * 2)
    ratio = min(inner / logo.width, inner / logo.height)
    target_w = max(1, int(logo.width * ratio))
    target_h = max(1, int(logo.height * ratio))
    logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
    x = (master_size - target_w) // 2
    y = (master_size - target_h) // 2
    canvas.paste(logo, (x, y), logo)
    return canvas


def _wide_tile(master: Image.Image, width: int, height: int) -> Image.Image:
    canvas = Image.new('RGBA', (width, height), (255, 255, 255, 255))
    logo = master.resize((height, height), Image.Resampling.LANCZOS)
    x = max(0, (width - logo.width) // 2)
    y = 0
    canvas.paste(logo, (x, y), logo)
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description='Build MSIX Store logo assets')
    parser.add_argument('--icon', type=Path, required=True, help='Source PNG icon')
    parser.add_argument('--out', type=Path, required=True, help='Output Assets directory')
    args = parser.parse_args()

    if not args.icon.is_file():
        raise SystemExit(f'Icon not found: {args.icon}')

    args.out.mkdir(parents=True, exist_ok=True)
    master = _square_icon(args.icon, 512)

    for filename, size in STORE_SIZES.items():
        if filename == 'Wide310x150Logo.png':
            image = _wide_tile(master, size[0], size[1])
        else:
            image = master.resize(size, Image.Resampling.LANCZOS)
        image.save(args.out / filename, format='PNG')

    print(f'Wrote Store assets to {args.out}')


if __name__ == '__main__':
    main()

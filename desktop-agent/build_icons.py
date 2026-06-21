#!/usr/bin/env python3
"""Regenerate agent_icon.ico/png from the official agent artwork."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
ASSETS = ROOT / 'assets'
ICON_SOURCES = (
    ASSETS / 'agent_icon_source.png',
    REPO / 'agent_icon.png',
)
LOGO_HEADER_SRC = REPO / 'accounts' / 'static' / 'accounts' / 'img' / 'ig-logo-light.png'
OUT_PNG = ASSETS / 'agent_icon.png'
OUT_ICO = ASSETS / 'agent_icon.ico'
OUT_LOGO = ASSETS / 'ig-logo-light.png'
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _resolve_icon_source() -> Path:
    for path in ICON_SOURCES:
        if path.is_file():
            return path
    raise SystemExit(
        'Missing agent icon source. Add desktop-agent/assets/agent_icon_source.png '
        'or agent_icon.png at the repo root.',
    )


def _crop_to_content(image: Image.Image) -> Image.Image:
    bbox = image.getbbox()
    if not bbox:
        return image
    return image.crop(bbox)


def _square_icon(source: Path, master_size: int = 512) -> Image.Image:
    """Fit the provided artwork into a square icon (taskbar, tray, window)."""
    logo = _crop_to_content(Image.open(source).convert('RGBA'))
    canvas = Image.new('RGBA', (master_size, master_size), (0, 0, 0, 0))
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


def main() -> None:
    source = _resolve_icon_source()
    ASSETS.mkdir(parents=True, exist_ok=True)

    master = _square_icon(source, 512)
    master.save(OUT_PNG)

    layers = [master.resize((size, size), Image.Resampling.LANCZOS) for size in ICO_SIZES]
    layers[-1].save(
        OUT_ICO,
        format='ICO',
        sizes=[(layer.width, layer.height) for layer in layers],
        append_images=layers[:-1],
    )

    if LOGO_HEADER_SRC.is_file():
        header = _crop_to_content(Image.open(LOGO_HEADER_SRC).convert('RGBA'))
        header.save(OUT_LOGO)

    print(f'Built from {source.name}: {OUT_PNG.name}, {OUT_ICO.name}')


if __name__ == '__main__':
    main()

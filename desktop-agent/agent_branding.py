"""IG E-Sign Agent branding assets (tray + window icon)."""

from __future__ import annotations

import sys
from pathlib import Path


def _bundle_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def agent_icon_paths() -> tuple[Path, ...]:
    agent_root = Path(__file__).resolve().parent
    bundle = _bundle_dir()
    return (
        bundle / 'desktop-agent' / 'assets' / 'agent_icon.png',
        agent_root / 'assets' / 'agent_icon.png',
        bundle / 'desktop-agent' / 'assets' / 'agent_icon.ico',
        agent_root / 'assets' / 'agent_icon.ico',
        agent_root.parent / 'agent_icon.png',
    )


def resolve_agent_icon_path(*, prefer_ico: bool = False) -> Path | None:
    paths = agent_icon_paths()
    if prefer_ico:
        paths = tuple(
            sorted(paths, key=lambda path: 0 if path.suffix.lower() == '.ico' else 1),
        )
    for path in paths:
        if path.is_file():
            return path
    return None


def load_agent_icon_image(*, alert: bool = False, size: int = 64):
    from PIL import Image, ImageDraw

    icon_path = resolve_agent_icon_path()
    if icon_path is not None:
        image = Image.open(icon_path).convert('RGBA')
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        if alert:
            overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.ellipse(
                (2, 2, image.size[0] - 2, image.size[1] - 2),
                outline=(220, 60, 60, 255),
                width=4,
            )
            image = Image.alpha_composite(image, overlay)
        return image

    image = Image.new('RGBA', (size, size), (37, 99, 235, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((14, 14, size - 14, size - 14), fill=(255, 255, 255, 255))
    draw.text((20, 22), 'IG', fill=(37, 99, 235, 255))
    if alert:
        draw.ellipse((2, 2, size - 2, size - 2), outline=(220, 60, 60, 255), width=4)
    return image


def apply_tk_window_icon(root) -> None:
    """Set the dashboard window icon where the platform supports it."""
    ico = resolve_agent_icon_path(prefer_ico=True)
    if ico is not None and ico.suffix.lower() == '.ico':
        try:
            root.iconbitmap(str(ico))
            return
        except Exception:
            pass

    png = resolve_agent_icon_path(prefer_ico=False)
    if png is None or png.suffix.lower() != '.png':
        return
    try:
        icon = root._tk.PhotoImage(file=str(png))  # type: ignore[attr-defined]
    except Exception:
        return
    try:
        root.iconphoto(True, icon)
    except Exception:
        return
    root._ig_icon_ref = icon  # prevent GC

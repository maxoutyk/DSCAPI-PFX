"""IG E-Sign Agent branding assets (tray, window, and UI logos)."""

from __future__ import annotations

import sys
from pathlib import Path

APP_USER_MODEL_ID = 'InciteGravity.IGEsignAgent.1'
_ICON_MASTER: object | None = None
_IDENTITY_CONFIGURED = False


def _bundle_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def _agent_assets_dir() -> Path:
    return Path(__file__).resolve().parent / 'assets'


def configure_windows_app_identity() -> None:
    """Ensure the taskbar uses our icon instead of the generic Python icon."""
    global _IDENTITY_CONFIGURED
    if _IDENTITY_CONFIGURED or sys.platform != 'win32':
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        _IDENTITY_CONFIGURED = True
    except Exception:
        pass


def agent_icon_paths() -> tuple[Path, ...]:
    agent_root = Path(__file__).resolve().parent
    bundle = _bundle_dir()
    paths: list[Path] = [
        agent_root / 'assets' / 'agent_icon.ico',
        agent_root / 'assets' / 'agent_icon.png',
        bundle / 'desktop-agent' / 'assets' / 'agent_icon.ico',
        bundle / 'desktop-agent' / 'assets' / 'agent_icon.png',
    ]
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        paths.extend(
            [
                exe_dir / 'agent_icon.ico',
                exe_dir / 'desktop-agent' / 'assets' / 'agent_icon.ico',
                exe_dir / '_internal' / 'desktop-agent' / 'assets' / 'agent_icon.ico',
            ],
        )
    paths.append(agent_root.parent / 'agent_icon.png')
    return tuple(paths)


def agent_logo_paths() -> tuple[Path, ...]:
    agent_root = Path(__file__).resolve().parent
    bundle = _bundle_dir()
    return (
        agent_root / 'assets' / 'ig-logo-light.png',
        bundle / 'desktop-agent' / 'assets' / 'ig-logo-light.png',
        bundle / 'accounts' / 'static' / 'accounts' / 'img' / 'ig-logo-light.png',
        agent_root.parent / 'accounts' / 'static' / 'accounts' / 'img' / 'ig-logo-light.png',
    )


def resolve_agent_icon_path(*, prefer_ico: bool = False) -> Path | None:
    paths = agent_icon_paths()
    if prefer_ico:
        paths = tuple(sorted(paths, key=lambda path: 0 if path.suffix.lower() == '.ico' else 1))
    for path in paths:
        if path.is_file():
            return path.resolve()
    return None


def resolve_agent_logo_path() -> Path | None:
    for path in agent_logo_paths():
        if path.is_file():
            return path.resolve()
    return None


def _load_icon_master():
    global _ICON_MASTER
    if _ICON_MASTER is not None:
        return _ICON_MASTER

    from PIL import Image

    icon_path = resolve_agent_icon_path(prefer_ico=False)
    if icon_path is not None and icon_path.suffix.lower() == '.png':
        with Image.open(icon_path) as img:
            _ICON_MASTER = img.convert('RGBA').copy()
        return _ICON_MASTER

    ico_path = resolve_agent_icon_path(prefer_ico=True)
    if ico_path is not None:
        with Image.open(ico_path) as img:
            _ICON_MASTER = img.convert('RGBA').copy()
        return _ICON_MASTER

    return None


def load_agent_icon_image(*, alert: bool = False, size: int = 256):
    from PIL import Image, ImageDraw

    master = _load_icon_master()
    if master is not None:
        if master.size[0] != size or master.size[1] != size:
            image = master.resize((size, size), Image.Resampling.LANCZOS)
        else:
            image = master.copy()
        if alert:
            overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.ellipse(
                (2, 2, image.size[0] - 2, image.size[1] - 2),
                outline=(218, 41, 28, 255),
                width=max(3, size // 32),
            )
            image = Image.alpha_composite(image, overlay)
        return image

    image = Image.new('RGBA', (size, size), (255, 102, 0, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, size - 8, size - 8), radius=12, fill=(255, 102, 0, 255))
    draw.text((size // 3, size // 3), 'IG', fill=(255, 255, 255, 255))
    if alert:
        draw.ellipse((2, 2, size - 2, size - 2), outline=(218, 41, 28, 255), width=max(3, size // 32))
    return image


def load_header_logo_image(*, max_width: int = 176, max_height: int = 44):
    from PIL import Image

    logo_path = resolve_agent_logo_path()
    if logo_path is None:
        return load_agent_icon_image(size=min(max_width, max_height))

    logo = Image.open(logo_path).convert('RGBA')
    bbox = logo.getbbox()
    if bbox:
        logo = logo.crop(bbox)
    ratio = min(max_width / logo.width, max_height / logo.height, 1.0)
    if ratio < 1.0:
        logo = logo.resize(
            (max(1, int(logo.width * ratio)), max(1, int(logo.height * ratio))),
            Image.Resampling.LANCZOS,
        )
    return logo


def apply_tk_window_icon(root) -> None:
    """Set the dashboard and taskbar icon on Windows."""
    configure_windows_app_identity()

    ico = resolve_agent_icon_path(prefer_ico=True)
    if ico is not None and ico.suffix.lower() == '.ico':
        ico_str = str(ico)
        try:
            root.iconbitmap(default=ico_str)
            root.wm_iconbitmap(True, ico_str)
            return
        except Exception:
            pass

    png = resolve_agent_icon_path(prefer_ico=False)
    if png is None or png.suffix.lower() != '.png':
        png_path = _agent_assets_dir() / 'agent_icon.png'
        if png_path.is_file():
            png = png_path.resolve()
        else:
            return

    try:
        from PIL import Image, ImageTk

        with Image.open(png) as img:
            image = img.convert('RGBA')
        if image.size[0] != 256:
            image = image.resize((256, 256), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
    except Exception:
        try:
            photo = root._tk.PhotoImage(file=str(png))  # type: ignore[attr-defined]
        except Exception:
            return

    try:
        root.iconphoto(True, photo)
    except Exception:
        return
    root._ig_icon_ref = photo  # prevent GC

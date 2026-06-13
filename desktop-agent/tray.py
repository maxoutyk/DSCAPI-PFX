"""Windows system tray UI for the IG E-Sign desktop agent."""

from __future__ import annotations

import threading
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

from agent import AGENT_VERSION, CONFIG_PATH, load_config, token_present


@dataclass
class AgentRuntimeState:
    port: int = 9765
    paired: bool = False
    api_base: str = ''
    portal_connected: bool = False
    token_present: bool = False
    last_error: str = ''
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                'port': self.port,
                'paired': self.paired,
                'api_base': self.api_base,
                'portal_connected': self.portal_connected,
                'token_present': self.token_present,
                'last_error': self.last_error,
            }

    def update(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)


def _bundle_dir() -> Path:
    import sys

    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def _load_icon_image(*, alert: bool = False):
    from PIL import Image, ImageDraw

    candidates = (
        _bundle_dir() / 'signPdf' / 'assets' / 'green-tick.png',
        Path(__file__).resolve().parent.parent / 'signPdf' / 'assets' / 'green-tick.png',
    )
    for path in candidates:
        if path.is_file():
            image = Image.open(path).convert('RGBA')
            image.thumbnail((64, 64))
            if alert:
                overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                draw.ellipse((2, 2, image.size[0] - 2, image.size[1] - 2), outline=(220, 60, 60, 255), width=4)
                image = Image.alpha_composite(image, overlay)
            return image

    image = Image.new('RGBA', (64, 64), (37, 99, 235, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((14, 14, 50, 50), fill=(255, 255, 255, 255))
    draw.text((20, 22), 'IG', fill=(37, 99, 235, 255))
    if alert:
        draw.ellipse((2, 2, 62, 62), outline=(220, 60, 60, 255), width=4)
    return image


def _status_lines(state: AgentRuntimeState) -> tuple[str, str, str]:
    snap = state.snapshot()
    if not snap['paired']:
        return (
            'Status: Not paired',
            'Run Pair Agent.bat from the install folder.',
            'error',
        )
    if snap['portal_connected']:
        status = f"Status: Connected ({snap['api_base']})"
        level = 'ok'
    else:
        detail = snap['last_error'] or 'portal unreachable'
        status = f'Status: Offline ({detail})'
        level = 'warn'
    token_line = 'USB token: detected' if snap['token_present'] else 'USB token: not detected'
    return status, token_line, level


def run_tray_loop(*, state: AgentRuntimeState, on_quit) -> None:
    import pystray

    icon_holder: dict[str, pystray.Icon | None] = {'icon': None}
    stop_event = threading.Event()

    def refresh_menu(icon: pystray.Icon):
        status_line, token_line, level = _status_lines(state)
        icon.icon = _load_icon_image(alert=level != 'ok')
        icon.title = f'IG E-Sign Agent v{AGENT_VERSION}'
        icon.menu = pystray.Menu(
            pystray.MenuItem(f'IG E-Sign Agent v{AGENT_VERSION}', None, enabled=False),
            pystray.MenuItem(status_line, None, enabled=False),
            pystray.MenuItem(token_line, None, enabled=False),
            pystray.MenuItem(f'Listening on 127.0.0.1:{state.port}', None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Open USB Agent page', _open_portal_page),
            pystray.MenuItem('Open config folder', _open_config_folder),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', _quit),
        )

    def _open_portal_page(_icon, _item):
        snap = state.snapshot()
        base = snap['api_base'] or load_config().get('api_base', '')
        if base:
            webbrowser.open(f'{base.rstrip("/")}/dashboard/agent/')

    def _open_config_folder(_icon, _item):
        import os
        import subprocess
        import sys

        folder = str(CONFIG_PATH.parent)
        if sys.platform == 'win32':
            os.startfile(folder)  # noqa: S606
        elif sys.platform == 'darwin':
            subprocess.run(['open', folder], check=False)
        else:
            subprocess.run(['xdg-open', folder], check=False)

    def _quit(icon, _item):
        stop_event.set()
        on_quit()
        icon.stop()

    def _refresh_loop(icon: pystray.Icon):
        while not stop_event.is_set():
            snap = state.snapshot()
            if snap['paired']:
                state.update(token_present=token_present())
            refresh_menu(icon)
            stop_event.wait(5)

    status_line, token_line, level = _status_lines(state)
    icon = pystray.Icon(
        'ig-esign-agent',
        _load_icon_image(alert=level != 'ok'),
        f'IG E-Sign Agent v{AGENT_VERSION}',
        menu=pystray.Menu(
            pystray.MenuItem(f'IG E-Sign Agent v{AGENT_VERSION}', None, enabled=False),
            pystray.MenuItem(status_line, None, enabled=False),
            pystray.MenuItem(token_line, None, enabled=False),
            pystray.MenuItem(f'Listening on 127.0.0.1:{state.port}', None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Open USB Agent page', _open_portal_page),
            pystray.MenuItem('Open config folder', _open_config_folder),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', _quit),
        ),
    )
    icon_holder['icon'] = icon
    threading.Thread(target=_refresh_loop, args=(icon,), daemon=True).start()
    icon.run()

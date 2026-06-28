"""Windows system tray UI for the IG E-Sign desktop agent."""

from __future__ import annotations

import threading
import webbrowser
from dataclasses import dataclass, field

from agent import AGENT_VERSION, CONFIG_PATH, load_config, token_present
from agent_branding import load_agent_icon_image
from app_ui_helpers import humanize_agent_error

TRAY_REFRESH_SECONDS = 4


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


def _load_icon_image(*, alert: bool = False):
    return load_agent_icon_image(alert=alert, size=256)


def _status_lines(state: AgentRuntimeState) -> tuple[str, str, str]:
    snap = state.snapshot()
    if not load_config().get('device_token'):
        return (
            'Status: Not paired',
            'Open the agent window to enter a pairing code.',
            'error',
        )
    if snap['portal_connected']:
        status = f"Status: Connected ({snap['api_base']})"
        level = 'ok'
    else:
        detail = humanize_agent_error(snap['last_error'] or 'portal unreachable')
        status = f'Status: Offline ({detail})'
        level = 'warn'
    token_line = _token_status_line(snap)
    return status, token_line, level


def _token_status_line(snap: dict) -> str:
    try:
        from pkcs11_signing import saved_token_display

        if not snap.get('token_present'):
            return 'USB token: not detected'
        display = saved_token_display()
        if display:
            return f'USB token: {display}'
        return 'USB token: detected'
    except Exception:
        return 'USB token: detected' if snap.get('token_present') else 'USB token: not detected'


def _confirm_quit_windows() -> bool:
    import sys

    if sys.platform != 'win32':
        return True
    try:
        import ctypes

        # MB_YESNO | MB_ICONQUESTION
        result = ctypes.windll.user32.MessageBoxW(
            0,
            'Stop the IG E-Sign Agent? USB signing from the portal will not work until you start it again.',
            'Quit IG E-Sign Agent',
            0x34,
        )
        return result == 6  # IDYES
    except Exception:
        return True


def run_tray_loop(
    *,
    state: AgentRuntimeState,
    on_quit,
    on_show_window=None,
    on_navigate_page=None,
    icon_registry=None,
) -> None:
    import pystray

    registry: dict[str, pystray.Icon | None] = icon_registry if icon_registry is not None else {}
    stop_event = threading.Event()

    def refresh_menu(icon: pystray.Icon):
        status_line, token_line, level = _status_lines(state)
        icon.icon = _load_icon_image(alert=level != 'ok')
        icon.title = f'IG E-Sign Agent v{AGENT_VERSION}'
        menu_items = [
            pystray.MenuItem(f'IG E-Sign Agent v{AGENT_VERSION}', None, enabled=False),
            pystray.MenuItem(status_line, None, enabled=False),
            pystray.MenuItem(token_line, None, enabled=False),
            pystray.MenuItem(f'Listening on 127.0.0.1:{state.port}', None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]
        if on_show_window is not None:
            menu_items.append(pystray.MenuItem('Open agent window', _show_window))
        if on_navigate_page is not None:
            menu_items.extend(
                [
                    pystray.MenuItem('Token & PIN settings', lambda *_args: _navigate('token')),
                    pystray.MenuItem('Allowed origins', lambda *_args: _navigate('origins')),
                ]
            )
        menu_items.extend(
            [
                pystray.MenuItem('Open USB Agent page', _open_portal_page),
                pystray.MenuItem('Open config folder', _open_config_folder),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('Quit', _quit),
            ]
        )
        icon.menu = pystray.Menu(*menu_items)

    def _navigate(page_id: str):
        if on_navigate_page is not None:
            if on_show_window is not None:
                on_show_window()
            on_navigate_page(page_id)

    def _show_window(_icon, _item):
        if on_show_window is not None:
            on_show_window()

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
        if not _confirm_quit_windows():
            return
        stop_event.set()
        on_quit()
        icon.stop()

    def _refresh_loop(icon: pystray.Icon):
        while not stop_event.is_set():
            snap = state.snapshot()
            if snap['paired']:
                state.update(token_present=token_present())
            refresh_menu(icon)
            stop_event.wait(TRAY_REFRESH_SECONDS)

    status_line, token_line, level = _status_lines(state)
    initial_menu = [
        pystray.MenuItem(f'IG E-Sign Agent v{AGENT_VERSION}', None, enabled=False),
        pystray.MenuItem(status_line, None, enabled=False),
        pystray.MenuItem(token_line, None, enabled=False),
        pystray.MenuItem(f'Listening on 127.0.0.1:{state.port}', None, enabled=False),
        pystray.Menu.SEPARATOR,
    ]
    if on_show_window is not None:
        initial_menu.append(pystray.MenuItem('Open agent window', _show_window))
    if on_navigate_page is not None:
        initial_menu.extend(
            [
                pystray.MenuItem('Token & PIN settings', lambda *_args: _navigate('token')),
                pystray.MenuItem('Allowed origins', lambda *_args: _navigate('origins')),
            ]
        )
    initial_menu.extend(
        [
            pystray.MenuItem('Open USB Agent page', _open_portal_page),
            pystray.MenuItem('Open config folder', _open_config_folder),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', _quit),
        ]
    )
    icon = pystray.Icon(
        'ig-esign-agent',
        _load_icon_image(alert=level != 'ok'),
        f'IG E-Sign Agent v{AGENT_VERSION}',
        menu=pystray.Menu(*initial_menu),
    )
    registry['icon'] = icon
    threading.Thread(target=_refresh_loop, args=(icon,), daemon=True).start()
    icon.run()

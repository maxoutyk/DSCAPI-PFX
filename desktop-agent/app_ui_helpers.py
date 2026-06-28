"""Shared UI helpers for the IG E-Sign Windows agent dashboard."""

from __future__ import annotations

import json
import re
from typing import Callable

from app_theme import ACCENT, BG, BORDER, DANGER, FONT, SUCCESS, SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, WARNING


def humanize_agent_error(raw: str) -> str:
    """Turn API or runtime errors into user-friendly status text."""
    text = (raw or '').strip()
    if not text:
        return 'Could not reach the portal. Check your network connection.'

    if 'revoked' in text.lower():
        return 'This device was revoked. Re-pair with a new code from the portal.'

    if text.startswith('{') or text.startswith('['):
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                for key in ('detail', 'message', 'error'):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        return humanize_agent_error(value)
        except json.JSONDecodeError:
            pass

    text = re.sub(r'\s+', ' ', text)
    if len(text) > 140:
        text = text[:137].rstrip() + '…'
    return text


class ScrollableFrame:
    """Vertical scroll container for dashboard pages."""

    def __init__(self, parent, *, padding=(0, 0)) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, borderwidth=0)
        self._scrollbar = ttk.Scrollbar(parent, orient='vertical', command=self._canvas.yview, style='Vertical.TScrollbar')
        self.inner = ttk.Frame(self._canvas, padding=padding)
        self._window_id = self._canvas.create_window((0, 0), window=self.inner, anchor='nw')

        self.inner.bind('<Configure>', self._on_inner_configure)
        self._canvas.bind('<Configure>', self._on_canvas_configure)
        self._canvas.configure(yscrollcommand=self._on_scrollbar)

        self._canvas.pack(side='left', fill='both', expand=True)
        self._bind_mousewheel(self._canvas)

    def _on_inner_configure(self, _event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox('all'))
        self._update_scrollbar_visibility()

    def _on_canvas_configure(self, event):
        self._canvas.itemconfigure(self._window_id, width=event.width)
        self._update_scrollbar_visibility()

    def _on_scrollbar(self, first, last):
        self._scrollbar.set(first, last)
        self._update_scrollbar_visibility()

    def _update_scrollbar_visibility(self) -> None:
        self.inner.update_idletasks()
        content_height = self.inner.winfo_reqheight()
        viewport_height = max(self._canvas.winfo_height(), 1)
        if content_height > viewport_height + 2:
            if not self._scrollbar.winfo_ismapped():
                self._scrollbar.pack(side='right', fill='y')
        elif self._scrollbar.winfo_ismapped():
            self._scrollbar.pack_forget()

    def _bind_mousewheel(self, widget) -> None:
        def _on_mousewheel(event):
            if event.delta:
                widget.yview_scroll(int(-1 * (event.delta / 120)), 'units')
            elif event.num == 4:
                widget.yview_scroll(-1, 'units')
            elif event.num == 5:
                widget.yview_scroll(1, 'units')

        def _bind(_event):
            widget.bind_all('<MouseWheel>', _on_mousewheel)
            widget.bind_all('<Button-4>', _on_mousewheel)
            widget.bind_all('<Button-5>', _on_mousewheel)

        def _unbind(_event):
            widget.unbind_all('<MouseWheel>')
            widget.unbind_all('<Button-4>')
            widget.unbind_all('<Button-5>')

        widget.bind('<Enter>', _bind)
        widget.bind('<Leave>', _unbind)


class ToastController:
    """Inline non-blocking feedback bar (replaces most success messageboxes)."""

    TONES = {
        'info': (SURFACE, TEXT_PRIMARY, BORDER),
        'ok': ('#ecfdf5', SUCCESS, SUCCESS),
        'warn': ('#fffbeb', WARNING, WARNING),
        'error': ('#fef2f2', DANGER, DANGER),
    }

    def __init__(self, root, host) -> None:
        import tkinter as tk

        self._root = root
        self._host = host
        self._tk = tk
        self._job = None
        self.var = tk.StringVar(value='')
        self.frame = tk.Frame(host, bg=BG, highlightthickness=0)
        self.label = tk.Label(
            self.frame,
            textvariable=self.var,
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=(FONT, 9),
            anchor='w',
            padx=12,
            pady=8,
            wraplength=760,
            justify='left',
        )
        self.label.pack(fill='x')

    def show(self, message: str, *, tone: str = 'info', duration_ms: int = 4500) -> None:
        bg, fg, border = self.TONES.get(tone, self.TONES['info'])
        self.var.set(message)
        self.label.configure(bg=bg, fg=fg)
        self.frame.configure(highlightbackground=border, highlightthickness=1)
        self._host.pack(fill='x')
        self.frame.pack(fill='x', pady=(0, 8))
        if self._job:
            self._root.after_cancel(self._job)

        def hide():
            self.frame.pack_forget()
            self._host.pack_forget()
            self.var.set('')
            self._job = None

        if duration_ms > 0:
            self._job = self._root.after(duration_ms, hide)


def confirm_dialog(parent, *, title: str, message: str, confirm_label: str = 'Continue') -> bool:
    """Enterprise-style confirmation; returns True if user confirms."""
    import tkinter as tk
    from tkinter import ttk

    from app_theme import configure_styles

    result = {'ok': False}
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.grab_set()
    dialog.resizable(False, False)
    configure_styles(dialog)

    body = ttk.Frame(dialog, padding=20)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text=title, style='Title.TLabel', font=(FONT, 14, 'bold')).pack(anchor='w')
    ttk.Label(body, text=message, style='Subtitle.TLabel', wraplength=420, justify='left').pack(anchor='w', pady=(10, 16))

    actions = ttk.Frame(body)
    actions.pack(fill='x')

    def accept():
        result['ok'] = True
        dialog.destroy()

    def cancel():
        dialog.destroy()

    ttk.Button(actions, text='Cancel', style='Secondary.TButton', command=cancel).pack(side='right')
    ttk.Button(actions, text=confirm_label, style='Danger.TButton', command=accept).pack(side='right', padx=(0, 8))
    dialog.bind('<Escape>', lambda _event: cancel())
    dialog.protocol('WM_DELETE_WINDOW', cancel)

    parent.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() // 2) - 230
    y = parent.winfo_rooty() + (parent.winfo_height() // 2) - 80
    dialog.geometry(f'460x180+{max(x, 0)}+{max(y, 0)}')
    dialog.wait_window()
    return result['ok']


def debounce(root, delay_ms: int, callback: Callable[[], None]) -> Callable[[], None]:
    job = {'id': None}

    def schedule():
        if job['id'] is not None:
            root.after_cancel(job['id'])
        job['id'] = root.after(delay_ms, _run)

    def _run():
        job['id'] = None
        callback()

    return schedule

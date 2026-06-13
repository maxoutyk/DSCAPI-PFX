"""Main dashboard window for the IG E-Sign Windows agent."""

from __future__ import annotations

import threading
import webbrowser
from typing import Callable

from agent import (
    AGENT_VERSION,
    CONFIG_PATH,
    clear_pairing,
    is_revoked_token_error,
    load_config,
    read_default_api_base,
    token_present,
    try_pair_agent,
)
from tray import AgentRuntimeState


PairCallback = Callable[[str, str], tuple[bool, str, str]]
QuitCallback = Callable[[], None]


class AgentDashboard:
    def __init__(
        self,
        *,
        state: AgentRuntimeState,
        on_pair: PairCallback | None = None,
        on_quit: QuitCallback | None = None,
    ):
        import tkinter as tk
        from tkinter import messagebox, ttk

        self._tk = tk
        self._ttk = ttk
        self._messagebox = messagebox
        self.state = state
        self.on_pair = on_pair or try_pair_agent
        self.on_quit = on_quit
        self._hidden = False
        self._refresh_job = None
        self._token_refresh_running = False

        self.root = tk.Tk()
        self.root.title('IG E-Sign Agent')
        self.root.geometry('440x620')
        self.root.minsize(400, 560)
        self.root.protocol('WM_DELETE_WINDOW', self.hide_to_tray)

        from pkcs11_signing import register_main_ui_root

        register_main_ui_root(self.root)

        container = ttk.Frame(self.root, padding=16)
        container.pack(fill='both', expand=True)

        header = ttk.Frame(container)
        header.pack(fill='x')
        ttk.Label(header, text='IG E-Sign Agent', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(header, text=f'Version {AGENT_VERSION}', foreground='#666666').pack(anchor='w', pady=(2, 0))

        status_frame = ttk.LabelFrame(container, text='Status', padding=12)
        status_frame.pack(fill='x', pady=(16, 12))
        self.status_frame = status_frame
        self.status_var = tk.StringVar(value='Checking…')
        self.portal_var = tk.StringVar(value='Portal: —')
        self.token_var = tk.StringVar(value='USB token: —')
        self.port_var = tk.StringVar(value=f'Local service: 127.0.0.1:{state.port}')
        ttk.Label(status_frame, textvariable=self.status_var, wraplength=360).pack(anchor='w')
        ttk.Label(status_frame, textvariable=self.portal_var, wraplength=360).pack(anchor='w', pady=(6, 0))
        ttk.Label(status_frame, textvariable=self.token_var).pack(anchor='w', pady=(6, 0))
        ttk.Label(status_frame, textvariable=self.port_var).pack(anchor='w', pady=(6, 0))

        self.token_frame = ttk.LabelFrame(container, text='USB signing token', padding=12)
        self.token_frame.pack(fill='x', pady=(0, 12))
        self.token_count_var = tk.StringVar(value='Insert your USB token and click Refresh.')
        ttk.Label(self.token_frame, textvariable=self.token_count_var, wraplength=360).pack(anchor='w')
        self.token_choice_var = tk.StringVar()
        self.token_combo = ttk.Combobox(
            self.token_frame,
            textvariable=self.token_choice_var,
            state='readonly',
            width=48,
        )
        self.token_combo.pack(fill='x', pady=(8, 8))
        token_actions = ttk.Frame(self.token_frame)
        token_actions.pack(fill='x')
        ttk.Button(token_actions, text='Refresh tokens', command=lambda: self._refresh_usb_tokens(background=True)).pack(side='left')
        ttk.Button(token_actions, text='Use for signing', command=self._save_usb_token).pack(side='left', padx=(8, 0))
        self._usb_tokens = []

        self.pair_frame = ttk.LabelFrame(container, text='Pair with portal', padding=12)
        self.pair_frame.pack(fill='x', pady=(0, 12))

        ttk.Label(self.pair_frame, text='Portal URL').pack(anchor='w')
        self.api_base_var = tk.StringVar(value=self._initial_api_base())
        ttk.Entry(self.pair_frame, textvariable=self.api_base_var).pack(fill='x', pady=(4, 10))

        ttk.Label(self.pair_frame, text='Pairing code').pack(anchor='w')
        self.code_var = tk.StringVar()
        code_entry = ttk.Entry(self.pair_frame, textvariable=self.code_var)
        code_entry.pack(fill='x', pady=(4, 10))
        code_entry.bind('<Return>', lambda _event: self._pair())

        self.pair_button = ttk.Button(self.pair_frame, text='Pair agent', command=self._pair)
        self.pair_button.pack(anchor='w')

        self.paired_note = ttk.Label(
            self.pair_frame,
            text='Generate a pairing code in the portal under USB Agent.',
            foreground='#666666',
            wraplength=360,
        )
        self.paired_note.pack(anchor='w', pady=(8, 0))

        actions = ttk.LabelFrame(container, text='Actions', padding=12)
        self.actions_frame = actions
        actions.pack(fill='x', pady=(0, 12))
        ttk.Button(actions, text='Open USB Agent page in browser', command=self._open_portal_page).pack(fill='x')
        ttk.Button(actions, text='Re-pair with portal', command=self._unpair).pack(fill='x', pady=(8, 0))
        ttk.Button(actions, text='Open config folder', command=self._open_config_folder).pack(fill='x', pady=(8, 0))
        ttk.Button(actions, text='Quit agent', command=self._quit).pack(fill='x', pady=(8, 0))

        ttk.Label(
            container,
            text='Closing this window keeps the agent running in the system tray.',
            foreground='#666666',
            wraplength=360,
        ).pack(anchor='w')

        self._refresh_view()
        self._refresh_usb_tokens(background=True)
        self._schedule_refresh()

    def _initial_api_base(self) -> str:
        config = load_config()
        return config.get('api_base') or read_default_api_base()

    def _refresh_usb_tokens(self, *, background: bool = True):
        if self._token_refresh_running:
            return

        def worker():
            from pkcs11_signing import refresh_usb_tokens

            try:
                tokens = refresh_usb_tokens()
            except Exception:
                tokens = []
            self.root.after(0, lambda: self._apply_usb_tokens(tokens))

        self._token_refresh_running = True
        self.token_count_var.set('Scanning USB tokens…')
        if background:
            threading.Thread(target=worker, daemon=True, name='ig-agent-token-scan').start()
        else:
            worker()

    def _apply_usb_tokens(self, tokens):
        from pkcs11_signing import format_token_display, match_saved_token

        self._token_refresh_running = False
        self._usb_tokens = tokens
        if not tokens:
            self.token_count_var.set('No USB token detected. Insert your token and click Refresh.')
            self.token_combo['values'] = ()
            self.token_choice_var.set('')
            self._refresh_view()
            return

        if len(tokens) == 1:
            self.token_count_var.set('Select the token to use for signing.')
        else:
            self.token_count_var.set('Multiple tokens found. Select which one to use.')

        labels = [format_token_display(token) for token in tokens]
        self.token_combo['values'] = labels
        matched = match_saved_token(tokens)
        self.token_choice_var.set(matched.display_name() if matched is not None else labels[0])
        self._refresh_view()

    def _save_usb_token(self):
        from pkcs11_signing import save_token_preference

        if not self._usb_tokens:
            self._messagebox.showerror('USB token', 'No USB tokens detected. Insert a token and click Refresh.')
            return
        selected = self.token_choice_var.get().strip()
        token = next((item for item in self._usb_tokens if item.display_name() == selected), None)
        if token is None:
            self._messagebox.showerror('USB token', 'Select a token from the list.')
            return
        save_token_preference(
            token.slot_id,
            label=token.label,
            serial=token.serial,
            signer_name=token.signer_name,
        )
        self._messagebox.showinfo('USB token', f'Using {token.display_name()} for signing.')
        self._refresh_view()

    def _selected_token_line(self, snap: dict) -> str:
        from pkcs11_signing import saved_token_display

        if not snap.get('token_present'):
            return 'USB token: not detected'
        display = saved_token_display()
        if display:
            return f'USB token: {display}'
        if self._usb_tokens:
            if len(self._usb_tokens) == 1:
                return f'USB token: {self._usb_tokens[0].display_name()}'
            return 'USB token: detected — select one below'
        return 'USB token: detected'

    def _schedule_refresh(self):
        self._refresh_view()
        self._refresh_job = self.root.after(4000, self._schedule_refresh)

    def _refresh_view(self):
        snap = self.state.snapshot()
        config = load_config()
        has_token = bool(config.get('device_token'))
        revoked = is_revoked_token_error(snap['last_error'])
        show_pairing = not has_token or revoked

        if show_pairing and not has_token:
            self.status_var.set('Not paired — enter a pairing code from the portal.')
            self.portal_var.set('Portal: not connected')
            self.token_var.set('USB token: —')
        elif show_pairing and revoked:
            self.status_var.set('This device was revoked. Generate a new pairing code and re-pair below.')
            self.portal_var.set(f"Portal: {config.get('api_base') or snap['api_base'] or '—'}")
            self.token_var.set('USB token: —')
        elif snap['portal_connected'] and has_token:
            self.status_var.set('Connected and ready to sign.')
            self.portal_var.set(f"Portal: {config.get('api_base') or snap['api_base'] or '—'}")
            self.token_var.set(self._selected_token_line(snap))
        else:
            detail = snap['last_error'] or 'portal unreachable'
            self.status_var.set(f'Paired but offline ({detail}).')
            self.portal_var.set(f"Portal: {config.get('api_base') or snap['api_base'] or '—'}")
            self.token_var.set(self._selected_token_line(snap))

        self.port_var.set(f"Local service: 127.0.0.1:{snap['port']}")

        if show_pairing:
            if not self.pair_frame.winfo_ismapped():
                self.pair_frame.pack(fill='x', pady=(0, 12), before=self.actions_frame)
        else:
            self.pair_frame.pack_forget()

        if has_token and snap.get('token_present') is not False:
            self.state.update(paired=True, token_present=token_present())
        elif not has_token:
            self.state.update(paired=False, portal_connected=False, last_error='')

    def _pair(self):
        api_base = self.api_base_var.get().strip()
        code = self.code_var.get().strip()
        if not api_base:
            self._messagebox.showerror('Pairing', 'Enter your portal URL.')
            return
        if not code:
            self._messagebox.showerror('Pairing', 'Enter the pairing code from the USB Agent page.')
            return

        self.pair_button.configure(state='disabled')
        try:
            ok, message, tenant = self.on_pair(api_base, code)
        finally:
            self.pair_button.configure(state='normal')

        if not ok:
            self._messagebox.showerror('Pairing failed', message)
            return

        config = load_config()
        self.state.update(
            paired=True,
            api_base=config.get('api_base', api_base.rstrip('/')),
            portal_connected=True,
            last_error='',
        )
        self.code_var.set('')
        self._messagebox.showinfo('Paired', f'Connected to {tenant or "your portal"}.')
        self._refresh_view()

    def _unpair(self):
        clear_pairing()
        self.code_var.set('')
        self.api_base_var.set(self._initial_api_base())
        self._messagebox.showinfo(
            'Re-pair',
            'Local pairing cleared. Generate a new code in the portal USB Agent page, then enter it above.',
        )
        self._refresh_view()

    def _open_portal_page(self):
        snap = self.state.snapshot()
        base = snap['api_base'] or load_config().get('api_base') or self.api_base_var.get().strip()
        if not base:
            self._messagebox.showinfo('Portal', 'Pair the agent first or enter a portal URL.')
            return
        webbrowser.open(f'{base.rstrip("/")}/dashboard/agent/')

    def _open_config_folder(self):
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

    def hide_to_tray(self):
        self._hidden = True
        self.root.withdraw()

    def show(self):
        self._hidden = False
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(200, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()
        self._refresh_view()

    def _quit(self):
        if self._refresh_job:
            self.root.after_cancel(self._refresh_job)
        from pkcs11_signing import unregister_main_ui_root

        unregister_main_ui_root()
        if self.on_quit:
            self.on_quit()

    def run(self):
        self.root.mainloop()


def run_app_ui(
    *,
    state: AgentRuntimeState,
    on_pair: PairCallback | None = None,
    on_quit: QuitCallback | None = None,
) -> AgentDashboard:
    dashboard = AgentDashboard(state=state, on_pair=on_pair, on_quit=on_quit)
    dashboard.run()
    return dashboard

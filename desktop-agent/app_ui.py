"""Main dashboard window for the IG E-Sign Windows agent."""

from __future__ import annotations

import webbrowser
from typing import Callable

from agent import AGENT_VERSION, CONFIG_PATH, load_config, read_default_api_base, token_present, try_pair_agent
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

        self.root = tk.Tk()
        self.root.title('IG E-Sign Agent')
        self.root.geometry('440x520')
        self.root.minsize(400, 480)
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
        ttk.Button(actions, text='Open config folder', command=self._open_config_folder).pack(fill='x', pady=(8, 0))
        ttk.Button(actions, text='Quit agent', command=self._quit).pack(fill='x', pady=(8, 0))

        ttk.Label(
            container,
            text='Closing this window keeps the agent running in the system tray.',
            foreground='#666666',
            wraplength=360,
        ).pack(anchor='w')

        self._refresh_view()
        self._schedule_refresh()

    def _initial_api_base(self) -> str:
        config = load_config()
        return config.get('api_base') or read_default_api_base()

    def _schedule_refresh(self):
        self._refresh_view()
        self._refresh_job = self.root.after(4000, self._schedule_refresh)

    def _refresh_view(self):
        snap = self.state.snapshot()
        paired = snap['paired'] or bool(load_config().get('device_token'))
        if not paired:
            self.status_var.set('Not paired — enter a pairing code from the portal.')
            self.portal_var.set('Portal: not connected')
            self.token_var.set('USB token: —')
        elif snap['portal_connected']:
            self.status_var.set('Connected and ready to sign.')
            self.portal_var.set(f"Portal: {snap['api_base'] or load_config().get('api_base', '—')}")
            self.token_var.set(
                'USB token: detected' if snap['token_present'] else 'USB token: not detected — insert token before signing'
            )
        else:
            detail = snap['last_error'] or 'portal unreachable'
            self.status_var.set(f'Paired but offline ({detail}).')
            self.portal_var.set(f"Portal: {snap['api_base'] or load_config().get('api_base', '—')}")
            self.token_var.set(
                'USB token: detected' if snap['token_present'] else 'USB token: not detected'
            )

        self.port_var.set(f"Local service: 127.0.0.1:{snap['port']}")

        if paired:
            self.pair_frame.pack_forget()
        elif not self.pair_frame.winfo_ismapped():
            self.pair_frame.pack(fill='x', pady=(0, 12), before=self.actions_frame)

        if paired and snap.get('token_present') is not False:
            self.state.update(token_present=token_present())

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

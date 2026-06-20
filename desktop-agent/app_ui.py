"""Main dashboard window for the IG E-Sign Windows agent."""

from __future__ import annotations

import threading
import webbrowser
from typing import Callable

from agent import (
    AGENT_VERSION,
    CONFIG_PATH,
    OriginValidationError,
    add_allowed_origin,
    clear_pairing,
    is_revoked_token_error,
    list_extra_allowed_origins,
    load_config,
    portal_origin_from_config,
    read_default_api_base,
    remove_allowed_origin,
    token_present,
    try_pair_agent,
    normalize_origin,
)
from app_theme import BG, configure_styles
from tray import AgentRuntimeState


PairCallback = Callable[[str, str], tuple[bool, str, str]]
QuitCallback = Callable[[], None]

NAV_ITEMS = (
    ('status', 'Status'),
    ('token', 'USB token'),
    ('pair', 'Pair portal'),
    ('origins', 'ERP origins'),
    ('actions', 'Actions'),
)


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
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._active_page = 'status'

        self.root = tk.Tk()
        self.root.title('IG E-Sign Agent')
        self.root.geometry('960x640')
        self.root.minsize(860, 560)
        self.root.protocol('WM_DELETE_WINDOW', self.hide_to_tray)
        configure_styles(self.root)

        from agent_branding import apply_tk_window_icon

        apply_tk_window_icon(self.root)

        from pkcs11_signing import register_main_ui_root

        register_main_ui_root(self.root)

        shell = ttk.Frame(self.root)
        shell.pack(fill='both', expand=True)

        self._build_sidebar(shell)
        self._build_main(shell)

        self._refresh_view()
        self._refresh_usb_tokens(background=True)
        self._schedule_refresh()

    def _build_sidebar(self, parent) -> None:
        tk = self._tk
        ttk = self._ttk

        sidebar = ttk.Frame(parent, style='Sidebar.TFrame', width=232)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)

        brand = ttk.Frame(sidebar, style='SidebarBrand.TFrame', padding=(16, 18, 16, 12))
        brand.pack(fill='x')

        logo_frame = tk.Frame(brand, bg='#0a0f2e', highlightthickness=0)
        logo_frame.pack(anchor='w')
        self._set_header_logo(logo_frame)

        ttk.Label(brand, text='Desktop Agent', style='SidebarMuted.TLabel').pack(anchor='w', pady=(8, 0))
        ttk.Label(brand, text=f'v{AGENT_VERSION}', style='SidebarMuted.TLabel').pack(anchor='w', pady=(2, 0))

        nav = ttk.Frame(sidebar, style='Sidebar.TFrame', padding=(8, 12, 8, 8))
        nav.pack(fill='both', expand=True)
        for page_id, label in NAV_ITEMS:
            button = ttk.Button(
                nav,
                text=label,
                style='Nav.TButton',
                command=lambda pid=page_id: self._show_page(pid),
            )
            button.pack(fill='x', pady=2)
            self._nav_buttons[page_id] = button

        footer = ttk.Frame(sidebar, style='Sidebar.TFrame', padding=(16, 8, 16, 16))
        footer.pack(fill='x', side='bottom')
        self.sidebar_status = tk.StringVar(value='Checking…')
        status_label = ttk.Label(footer, textvariable=self.sidebar_status, style='SidebarMuted.TLabel', wraplength=190)
        status_label.pack(anchor='w')

    def _set_header_logo(self, parent) -> None:
        from agent_branding import load_header_logo_image

        try:
            from PIL import ImageTk

            logo = load_header_logo_image()
            photo = ImageTk.PhotoImage(logo)
            label = self._tk.Label(parent, image=photo, bg='#0a0f2e', borderwidth=0)
            label.image = photo
            label.pack(anchor='w')
            self._logo_ref = photo
        except Exception:
            self._tk.Label(
                parent,
                text='IG E-Sign',
                bg='#0a0f2e',
                fg='#f0f1f5',
                font=('Segoe UI', 14, 'bold'),
            ).pack(anchor='w')

    def _build_main(self, parent) -> None:
        ttk = self._ttk

        main = ttk.Frame(parent, padding=0)
        main.pack(side='left', fill='both', expand=True)

        topbar = ttk.Frame(main, padding=(24, 20, 24, 12))
        topbar.pack(fill='x')
        self.page_title = self._tk.StringVar(value='Status')
        ttk.Label(topbar, textvariable=self.page_title, style='Title.TLabel').pack(anchor='w')
        self.page_subtitle = self._tk.StringVar(value='Connection and signing readiness')
        ttk.Label(topbar, textvariable=self.page_subtitle, style='Subtitle.TLabel').pack(anchor='w', pady=(4, 0))

        body_host = ttk.Frame(main, padding=(24, 0, 24, 24))
        body_host.pack(fill='both', expand=True)

        canvas = self._tk.Canvas(body_host, bg=BG, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(body_host, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        self.content = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=self.content, anchor='nw')

        def _on_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
            canvas.itemconfigure(canvas_window, width=canvas.winfo_width())

        self.content.bind('<Configure>', _on_configure)
        canvas.bind('<Configure>', _on_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

        canvas.bind_all('<MouseWheel>', _on_mousewheel, add='+')

        self.pages: dict[str, ttk.Frame] = {}
        self._build_status_page()
        self._build_token_page()
        self._build_pair_page()
        self._build_origins_page()
        self._build_actions_page()
        self._show_page('status')

    def _page_frame(self, page_id: str) -> ttk.Frame:
        frame = self._ttk.Frame(self.content, padding=0)
        self.pages[page_id] = frame
        return frame

    def _card(self, parent, title: str) -> ttk.LabelFrame:
        return self._ttk.LabelFrame(parent, text=title, style='Card.TLabelframe', padding=16)

    def _build_status_page(self) -> None:
        page = self._page_frame('status')
        card = self._card(page, 'Agent status')
        card.pack(fill='x')

        self.status_var = self._tk.StringVar(value='Checking…')
        self.portal_var = self._tk.StringVar(value='Portal: —')
        self.token_var = self._tk.StringVar(value='USB token: —')
        self.port_var = self._tk.StringVar(value=f'Local service: 127.0.0.1:{self.state.port}')

        for var in (self.status_var, self.portal_var, self.token_var, self.port_var):
            self._ttk.Label(card, textvariable=var, style='Card.TLabel', wraplength=620).pack(anchor='w', pady=(0, 8))

        note = self._card(page, 'Tip')
        note.pack(fill='x', pady=(16, 0))
        self._ttk.Label(
            note,
            text='Closing this window keeps the agent running in the system tray near the clock.',
            style='CardMuted.TLabel',
            wraplength=620,
        ).pack(anchor='w')

    def _build_token_page(self) -> None:
        page = self._page_frame('token')
        self.token_frame = self._card(page, 'USB signing token')
        self.token_frame.pack(fill='x')

        self.token_count_var = self._tk.StringVar(value='Insert your USB token and click Refresh.')
        self._ttk.Label(self.token_frame, textvariable=self.token_count_var, style='CardMuted.TLabel', wraplength=620).pack(anchor='w')

        self.token_choice_var = self._tk.StringVar()
        self.token_combo = self._ttk.Combobox(
            self.token_frame,
            textvariable=self.token_choice_var,
            state='readonly',
            width=72,
        )
        self.token_combo.pack(fill='x', pady=(12, 12))

        actions = self._ttk.Frame(self.token_frame, style='Card.TFrame')
        actions.pack(fill='x')
        self._ttk.Button(actions, text='Refresh tokens', style='Secondary.TButton', command=lambda: self._refresh_usb_tokens(background=True)).pack(side='left')
        self._ttk.Button(actions, text='Use for signing', style='Primary.TButton', command=self._save_usb_token).pack(side='left', padx=(10, 0))
        self._usb_tokens = []

    def _build_pair_page(self) -> None:
        page = self._page_frame('pair')
        self.pair_frame = self._card(page, 'Pair with portal')
        self.pair_frame.pack(fill='x')

        self._ttk.Label(self.pair_frame, text='Portal URL', style='Card.TLabel').pack(anchor='w')
        self.api_base_var = self._tk.StringVar(value=self._initial_api_base())
        self._ttk.Entry(self.pair_frame, textvariable=self.api_base_var).pack(fill='x', pady=(6, 14))

        self._ttk.Label(self.pair_frame, text='Pairing code', style='Card.TLabel').pack(anchor='w')
        self.code_var = self._tk.StringVar()
        code_entry = self._ttk.Entry(self.pair_frame, textvariable=self.code_var)
        code_entry.pack(fill='x', pady=(6, 14))
        code_entry.bind('<Return>', lambda _event: self._pair())

        self.pair_button = self._ttk.Button(self.pair_frame, text='Pair agent', style='Primary.TButton', command=self._pair)
        self.pair_button.pack(anchor='w')

        self.paired_note = self._ttk.Label(
            self.pair_frame,
            text='Generate a pairing code in the portal under USB Agent.',
            style='CardMuted.TLabel',
            wraplength=620,
        )
        self.paired_note.pack(anchor='w', pady=(12, 0))

    def _build_origins_page(self) -> None:
        page = self._page_frame('origins')
        self.origins_frame = self._card(page, 'Allowed browser origins')
        self.origins_frame.pack(fill='x')

        self.portal_origin_var = self._tk.StringVar(value='Portal (automatic): —')
        self._ttk.Label(self.origins_frame, textvariable=self.portal_origin_var, style='Card.TLabel', wraplength=620).pack(anchor='w')
        self._ttk.Label(
            self.origins_frame,
            text='Add origins for ERP or web apps that call this agent (e.g. Business Central).',
            style='CardMuted.TLabel',
            wraplength=620,
        ).pack(anchor='w', pady=(8, 12))

        list_wrap = self._ttk.Frame(self.origins_frame, style='Card.TFrame')
        list_wrap.pack(fill='both', expand=True)
        self.origins_listbox = self._tk.Listbox(
            list_wrap,
            height=8,
            exportselection=False,
            bg='#121a3d',
            fg='#f0f1f5',
            selectbackground='#ff6600',
            selectforeground='#ffffff',
            highlightthickness=1,
            highlightbackground='#1a2248',
            borderwidth=0,
            activestyle='none',
        )
        self.origins_listbox.pack(side='left', fill='both', expand=True)
        origins_scroll = self._ttk.Scrollbar(list_wrap, orient='vertical', command=self.origins_listbox.yview)
        origins_scroll.pack(side='right', fill='y')
        self.origins_listbox.configure(yscrollcommand=origins_scroll.set)

        origin_entry_row = self._ttk.Frame(self.origins_frame, style='Card.TFrame')
        origin_entry_row.pack(fill='x', pady=(12, 0))
        self.origin_entry_var = self._tk.StringVar()
        self._ttk.Entry(origin_entry_row, textvariable=self.origin_entry_var).pack(side='left', fill='x', expand=True)
        self._ttk.Button(origin_entry_row, text='Add', style='Secondary.TButton', command=self._add_allowed_origin).pack(side='left', padx=(10, 0))
        self._ttk.Button(self.origins_frame, text='Remove selected', style='Secondary.TButton', command=self._remove_allowed_origin).pack(anchor='w', pady=(12, 0))

    def _build_actions_page(self) -> None:
        page = self._page_frame('actions')
        card = self._card(page, 'Quick actions')
        card.pack(fill='x')

        for label, command in (
            ('Open USB Agent page in browser', self._open_portal_page),
            ('Re-pair with portal', self._unpair),
            ('Open config folder', self._open_config_folder),
            ('Quit agent', self._quit),
        ):
            self._ttk.Button(card, text=label, style='Secondary.TButton', command=command).pack(fill='x', pady=(0, 10))

    def _show_page(self, page_id: str) -> None:
        subtitles = {
            'status': 'Connection and signing readiness',
            'token': 'Choose which USB DSC token to use',
            'pair': 'Connect this computer to your IG E-Sign portal',
            'origins': 'ERP and browser apps allowed to call the agent',
            'actions': 'Shortcuts and maintenance',
        }
        titles = dict(NAV_ITEMS)
        self._active_page = page_id
        self.page_title.set(titles.get(page_id, 'Agent'))
        self.page_subtitle.set(subtitles.get(page_id, ''))

        for pid, button in self._nav_buttons.items():
            button.configure(style='NavActive.TButton' if pid == page_id else 'Nav.TButton')

        for frame in self.pages.values():
            frame.pack_forget()
        self.pages[page_id].pack(fill='both', expand=True)

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

        self.token_count_var.set(
            'Select the token to use for signing.'
            if len(tokens) == 1
            else 'Multiple tokens found. Select which one to use.',
        )

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
            return 'USB token: detected — select one on the USB token page'
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
            self.sidebar_status.set('Not paired')
        elif show_pairing and revoked:
            self.status_var.set('This device was revoked. Generate a new pairing code and re-pair.')
            self.portal_var.set(f"Portal: {config.get('api_base') or snap['api_base'] or '—'}")
            self.token_var.set('USB token: —')
            self.sidebar_status.set('Revoked — re-pair')
        elif snap['portal_connected'] and has_token:
            self.status_var.set('Connected and ready to sign.')
            self.portal_var.set(f"Portal: {config.get('api_base') or snap['api_base'] or '—'}")
            self.token_var.set(self._selected_token_line(snap))
            self.sidebar_status.set('Connected')
        else:
            detail = snap['last_error'] or 'portal unreachable'
            self.status_var.set(f'Paired but offline ({detail}).')
            self.portal_var.set(f"Portal: {config.get('api_base') or snap['api_base'] or '—'}")
            self.token_var.set(self._selected_token_line(snap))
            self.sidebar_status.set('Offline')

        self.port_var.set(f"Local service: 127.0.0.1:{snap['port']}")

        if show_pairing and self._active_page == 'status' and not has_token:
            self._show_page('pair')

        if has_token and snap.get('token_present') is not False:
            self.state.update(paired=True, token_present=token_present())
        elif not has_token:
            self.state.update(paired=False, portal_connected=False, last_error='')

        self._refresh_origins_view()

    def _refresh_origins_view(self):
        config = load_config()
        portal = portal_origin_from_config(config)
        if portal:
            self.portal_origin_var.set(f'Portal (automatic): {portal}')
        else:
            self.portal_origin_var.set('Portal (automatic): — pair the agent first')

        extras = list_extra_allowed_origins(config)
        self.origins_listbox.delete(0, 'end')
        for origin in extras:
            self.origins_listbox.insert('end', origin)

    def _add_allowed_origin(self):
        origin = self.origin_entry_var.get().strip()
        if not origin:
            self._messagebox.showerror('Allowed origins', 'Enter an origin URL to add.')
            return
        try:
            add_allowed_origin(origin)
        except OriginValidationError as exc:
            self._messagebox.showerror('Allowed origins', str(exc))
            return
        self.origin_entry_var.set('')
        self._refresh_origins_view()
        self._messagebox.showinfo('Allowed origins', f'Added {normalize_origin(origin)}')

    def _remove_allowed_origin(self):
        selection = self.origins_listbox.curselection()
        if not selection:
            self._messagebox.showerror('Allowed origins', 'Select an origin to remove.')
            return
        origin = self.origins_listbox.get(selection[0])
        remove_allowed_origin(origin)
        self._refresh_origins_view()

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
        self._show_page('status')
        self._refresh_view()

    def _unpair(self):
        clear_pairing()
        self.code_var.set('')
        self.api_base_var.set(self._initial_api_base())
        self._messagebox.showinfo(
            'Re-pair',
            'Local pairing cleared. Generate a new code in the portal USB Agent page, then enter it on Pair portal.',
        )
        self._show_page('pair')
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

"""Main dashboard window for the IG E-Sign Windows agent."""

from __future__ import annotations

import sys
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
    save_config,
    token_present,
    try_pair_agent,
    normalize_origin,
)
from app_theme import (
    ACCENT,
    ACCENT_SOFT,
    BG,
    BORDER,
    DANGER,
    INFO_BG,
    SECTION_GAP,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
    configure_styles,
)
from app_ui_helpers import ScrollableFrame, ToastController, confirm_dialog, debounce, humanize_agent_error
from tray import AgentRuntimeState

PairCallback = Callable[[str, str], tuple[bool, str, str]]
QuitCallback = Callable[[], None]

REFRESH_MS = 4000

NAV_ITEMS = (
    ('status', 'Status'),
    ('token', 'Token & PIN'),
    ('pair', 'Pair portal'),
    ('origins', 'Allowed origins'),
    ('actions', 'Settings'),
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
        self._nav_rows: dict[str, ttk.Frame] = {}
        self._nav_indicators: dict[str, tk.Frame] = {}
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._active_page = 'status'
        self._pin_dirty = False
        self._pin_loading = False
        self._pair_running = False
        self._usb_tokens = []

        self.root = tk.Tk()
        self.root.title('IG E-Sign Agent')
        self.root.geometry('980x660')
        self.root.minsize(880, 580)
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

        self._debounced_pin_save = debounce(self.root, 600, self._flush_pin_settings)

        self._refresh_view()
        self._refresh_usb_tokens(background=True)
        self._load_pin_settings()
        self._schedule_refresh()

    # ------------------------------------------------------------------ layout

    def _build_sidebar(self, parent) -> None:
        tk = self._tk
        ttk = self._ttk

        sidebar = ttk.Frame(parent, style='Sidebar.TFrame', width=232)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        tk.Frame(parent, bg=BORDER, width=1).pack(side='left', fill='y')

        brand = ttk.Frame(sidebar, style='SidebarBrand.TFrame', padding=(16, 18, 16, 12))
        brand.pack(fill='x')

        logo_frame = tk.Frame(brand, bg=SURFACE, highlightthickness=0)
        logo_frame.pack(anchor='w')
        self._set_header_logo(logo_frame)

        ttk.Label(
            brand,
            text='IG E-Sign Agent',
            style='Sidebar.TLabel',
            font=('Segoe UI', 11, 'bold'),
        ).pack(anchor='w', pady=(10, 0))
        ttk.Label(brand, text='Desktop Agent', style='SidebarMuted.TLabel').pack(anchor='w', pady=(2, 0))
        ttk.Label(brand, text=f'v{AGENT_VERSION}', style='SidebarMuted.TLabel').pack(anchor='w', pady=(2, 0))

        nav = ttk.Frame(sidebar, style='Sidebar.TFrame', padding=(8, 12, 8, 8))
        nav.pack(fill='both', expand=True)
        for page_id, label in NAV_ITEMS:
            row = ttk.Frame(nav, style='NavRow.TFrame')
            row.pack(fill='x', pady=2)

            indicator = tk.Frame(row, width=3, bg=SURFACE, highlightthickness=0)
            indicator.pack(side='left', fill='y', padx=(0, 0))

            button = ttk.Button(
                row,
                text=label,
                style='Nav.TButton',
                takefocus=True,
                command=lambda pid=page_id: self._request_page(pid),
            )
            button.pack(side='left', fill='x', expand=True, padx=(0, 4))

            self._nav_rows[page_id] = row
            self._nav_indicators[page_id] = indicator
            self._nav_buttons[page_id] = button

        footer = ttk.Frame(sidebar, style='Sidebar.TFrame', padding=(16, 8, 16, 16))
        footer.pack(fill='x', side='bottom')
        self.sidebar_status = tk.StringVar(value='Checking…')
        self.sidebar_status_label = ttk.Label(
            footer,
            textvariable=self.sidebar_status,
            style='SidebarMuted.TLabel',
            wraplength=190,
        )
        self.sidebar_status_label.pack(anchor='w')

    def _set_header_logo(self, parent) -> None:
        from agent_branding import load_agent_icon_image

        try:
            from PIL import ImageTk

            logo = load_agent_icon_image(size=52)
            photo = ImageTk.PhotoImage(logo)
            label = self._tk.Label(parent, image=photo, bg=SURFACE, borderwidth=0)
            label.image = photo
            label.pack(anchor='w')
            self._logo_ref = photo
        except Exception:
            self._tk.Label(
                parent,
                text='IG',
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=('Segoe UI', 18, 'bold'),
            ).pack(anchor='w')

    def _build_main(self, parent) -> None:
        ttk = self._ttk

        main = ttk.Frame(parent, padding=0)
        main.pack(side='left', fill='both', expand=True)

        topbar = ttk.Frame(main, style='Main.TFrame', padding=(28, 22, 28, 0))
        topbar.pack(fill='x')
        self.page_title = self._tk.StringVar(value='Status')
        ttk.Label(topbar, textvariable=self.page_title, style='Title.TLabel').pack(anchor='w')
        self.page_subtitle = self._tk.StringVar(value='Connection and signing readiness')
        ttk.Label(topbar, textvariable=self.page_subtitle, style='Subtitle.TLabel').pack(anchor='w', pady=(6, 0))
        self._tk.Frame(topbar, bg=BORDER, height=1).pack(fill='x', pady=(16, 0))

        toast_host = ttk.Frame(main, style='Main.TFrame', padding=(28, 0, 28, 0))
        self.toast = ToastController(self.root, toast_host)

        body_host = ttk.Frame(main, style='Main.TFrame', padding=(28, 8, 28, 24))
        body_host.pack(fill='both', expand=True)

        self.content = ttk.Frame(body_host)
        self.content.pack(fill='both', expand=True)

        self.pages: dict[str, ttk.Frame] = {}
        self._scrollables: dict[str, ScrollableFrame] = {}
        self._build_status_page()
        self._build_token_page()
        self._build_pair_page()
        self._build_origins_page()
        self._build_actions_page()
        self._show_page('status')

    def _page_host(self, page_id: str) -> ttk.Frame:
        outer = self._ttk.Frame(self.content, padding=0)
        self.pages[page_id] = outer
        scroll = ScrollableFrame(outer, padding=(0, 0))
        self._scrollables[page_id] = scroll
        return scroll.inner

    def _section(self, parent, title: str):
        """Return (section container, inner panel) with external heading."""
        ttk = self._ttk
        tk = self._tk
        container = ttk.Frame(parent, style='TFrame')
        container.pack(fill='x', pady=(0, SECTION_GAP))
        ttk.Label(container, text=title.upper(), style='SectionHeading.TLabel').pack(anchor='w', pady=(0, 8))
        wrap = tk.Frame(container, bg=BORDER, highlightthickness=0)
        wrap.pack(fill='x')
        panel = ttk.Frame(wrap, style='Panel.TFrame', padding=18)
        panel.pack(fill='x', padx=1, pady=1)
        return container, panel

    def _panel(self, parent) -> ttk.Frame:
        tk = self._tk
        wrap = tk.Frame(parent, bg=BORDER, highlightthickness=0)
        wrap.pack(fill='x')
        inner = self._ttk.Frame(wrap, style='Panel.TFrame', padding=18)
        inner.pack(fill='x', padx=1, pady=1)
        return inner

    def _form_entry(self, parent, textvariable, **kwargs):
        entry = self._ttk.Entry(parent, textvariable=textvariable, style='Form.TEntry', **kwargs)
        entry.pack(fill='x', pady=(6, 14))
        return entry

    def _form_combobox(self, parent, textvariable, **kwargs):
        combo = self._ttk.Combobox(parent, textvariable=textvariable, style='Form.TCombobox', **kwargs)
        combo.pack(fill='x', pady=(0, 14))
        return combo

    def _form_listbox(self, parent, *, height: int = 4):
        tk = self._tk
        wrap = tk.Frame(parent, bg=BORDER, highlightthickness=0)
        wrap.pack(fill='x', pady=(0, 12))
        row = tk.Frame(wrap, bg=SURFACE, highlightthickness=0)
        row.pack(fill='x', padx=1, pady=1)
        listbox = tk.Listbox(
            row,
            height=height,
            exportselection=False,
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            selectbackground=ACCENT,
            selectforeground='#ffffff',
            highlightthickness=0,
            borderwidth=0,
            activestyle='none',
            font=('Segoe UI', 10),
        )
        listbox.pack(side='left', fill='x', expand=True, padx=2, pady=2)
        scroll = self._ttk.Scrollbar(row, orient='vertical', command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        return listbox, scroll, wrap

    def _readonly_box(self, parent) -> ttk.Frame:
        return self._ttk.Frame(parent, style='HighlightBox.TFrame', padding=(12, 10))

    def _kv_row(self, parent, label: str, var) -> None:
        row = self._ttk.Frame(parent, style='Panel.TFrame')
        row.pack(fill='x', pady=(0, 10))
        self._ttk.Label(row, text=label, style='FieldLabel.TLabel', width=14).pack(side='left', anchor='nw')
        self._ttk.Label(row, textvariable=var, style='FieldValue.TLabel', wraplength=480, justify='left').pack(
            side='left',
            fill='x',
            expand=True,
            anchor='w',
        )

    def _alert_banner(self, parent, *, title: str, body: str, tone: str = 'warn', body_var=None):
        tk = self._tk
        colors = {
            'warn': ('#fffbeb', WARNING, '#fde68a'),
            'info': (INFO_BG, TEXT_PRIMARY, BORDER),
        }
        bg, fg, border = colors.get(tone, colors['warn'])
        outer = tk.Frame(parent, bg=border, highlightthickness=0)
        inner = tk.Frame(outer, bg=bg, highlightthickness=0)
        inner.pack(fill='x', padx=1, pady=1)
        content = self._ttk.Frame(inner, style='Panel.TFrame', padding=(16, 14))
        content.pack(fill='x')
        self._tk.Label(content, text=title, bg=SURFACE, fg=fg, font=('Segoe UI', 10, 'bold'), anchor='w').pack(
            anchor='w',
        )
        body_kwargs = {'style': 'CardMuted.TLabel', 'wraplength': 640, 'justify': 'left'}
        if body_var is not None:
            body_label = self._ttk.Label(content, textvariable=body_var, **body_kwargs)
        else:
            body_label = self._ttk.Label(content, text=body, **body_kwargs)
        body_label.pack(anchor='w', pady=(6, 0))
        return outer, content

    def _badge_row(self, parent, label: str, var):
        tk = self._tk
        wrap = tk.Frame(parent, bg=BORDER, highlightthickness=0)
        wrap.pack(fill='x', pady=(0, 14))
        inner = tk.Frame(wrap, bg=ACCENT_SOFT, highlightthickness=0)
        inner.pack(fill='x', padx=1, pady=1)
        row = tk.Frame(inner, bg=ACCENT_SOFT, highlightthickness=0)
        row.pack(fill='x', padx=12, pady=10)
        tk.Label(row, text=label, bg=ACCENT_SOFT, fg=TEXT_SECONDARY, font=('Segoe UI', 9)).pack(side='left')
        tk.Label(row, textvariable=var, bg=ACCENT_SOFT, fg=TEXT_PRIMARY, font=('Segoe UI', 10, 'bold')).pack(
            side='left',
            padx=(8, 0),
        )
        return wrap

    # ------------------------------------------------------------------ status

    def _build_status_page(self) -> None:
        page = self._page_host('status')

        self._welcome_section, welcome_panel = self._section(page, 'Getting started')
        self._ttk.Label(
            welcome_panel,
            text='Pair with your portal, choose a USB token, and sign documents from your browser.',
            style='CardMuted.TLabel',
            wraplength=640,
            justify='left',
        ).pack(anchor='w', pady=(0, 12))
        self._ttk.Button(
            welcome_panel,
            text='Dismiss',
            style='Secondary.TButton',
            command=self._dismiss_welcome_banner,
        ).pack(anchor='w')

        self.update_banner_body_var = self._tk.StringVar(value='')
        self._update_banner_outer, self._update_banner = self._alert_banner(
            page,
            title='Update available',
            body='',
            tone='info',
            body_var=self.update_banner_body_var,
        )
        self._update_banner_outer.pack_forget()
        update_actions = self._ttk.Frame(self._update_banner, style='Panel.TFrame')
        update_actions.pack(anchor='w', pady=(12, 0))
        self._ttk.Button(
            update_actions,
            text='Download update',
            style='Primary.TButton',
            command=self._download_installer,
        ).pack(side='left')
        self._ttk.Button(
            update_actions,
            text='Dismiss',
            style='Secondary.TButton',
            command=self._dismiss_update_banner,
        ).pack(side='left', padx=(10, 0))

        self._pairing_banner_outer, self._pairing_banner = self._alert_banner(
            page,
            title='Pairing required',
            body='Enter a one-time code from the USB Agent page in your IG E-Sign portal.',
            tone='warn',
        )
        self._pairing_banner_outer.pack_forget()
        banner_actions = self._ttk.Frame(self._pairing_banner, style='Panel.TFrame')
        banner_actions.pack(anchor='w', pady=(12, 0))
        self._ttk.Button(
            banner_actions,
            text='Go to Pair portal',
            style='Primary.TButton',
            command=lambda: self.navigate_to('pair'),
        ).pack(side='left')
        self._ttk.Button(
            banner_actions,
            text='Open USB Agent page',
            style='Secondary.TButton',
            command=self._open_portal_page,
        ).pack(side='left', padx=(10, 0))

        self._status_section, status_panel = self._section(page, 'Overview')

        self.status_headline = self._tk.StringVar(value='Checking…')
        self.status_headline_label = self._ttk.Label(
            status_panel,
            textvariable=self.status_headline,
            style='StatusMuted.TLabel',
            wraplength=640,
        )
        self.status_headline_label.pack(anchor='w', pady=(0, 16))

        self.tenant_var = self._tk.StringVar(value='—')
        self.portal_var = self._tk.StringVar(value='—')
        self.token_var = self._tk.StringVar(value='—')
        self.pin_status_var = self._tk.StringVar(value='—')
        self.port_var = self._tk.StringVar(value=f'127.0.0.1:{self.state.port}')

        self._kv_row(status_panel, 'Organization', self.tenant_var)
        self._kv_row(status_panel, 'Portal', self.portal_var)
        self._kv_row(status_panel, 'USB token', self.token_var)
        self._kv_row(status_panel, 'PIN memory', self.pin_status_var)
        self._kv_row(status_panel, 'Local service', self.port_var)

        self._page_footer = self._ttk.Label(
            page,
            text='Closing this window keeps the agent running in the system tray. Right-click the tray icon to reopen or quit.',
            style='PageFooter.TLabel',
            wraplength=640,
            justify='left',
        )
        self._page_footer.pack(anchor='w', pady=(4, 0))

    def _dismiss_welcome_banner(self) -> None:
        config = load_config()
        config['ui_welcome_dismissed'] = True
        save_config(config)
        self._welcome_section.pack_forget()

    def _dismiss_update_banner(self) -> None:
        snap = self.state.snapshot()
        latest = (snap.get('latest_agent_version') or '').strip()
        config = load_config()
        if latest:
            config['ui_update_dismissed_version'] = latest
            save_config(config)
        self._update_banner_outer.pack_forget()

    def _update_welcome_banner(self) -> None:
        if load_config().get('ui_welcome_dismissed'):
            self._welcome_section.pack_forget()
        elif not self._welcome_section.winfo_ismapped():
            children = self._pages_inner('status').winfo_children()
            first = children[0] if children else None
            if first is not None:
                self._welcome_section.pack(fill='x', before=first)
            else:
                self._welcome_section.pack(fill='x')

    def _update_version_banner(self) -> None:
        snap = self.state.snapshot()
        latest = (snap.get('latest_agent_version') or '').strip()
        if not snap.get('update_available') or not latest:
            self._update_banner_outer.pack_forget()
            return
        config = load_config()
        if config.get('ui_update_dismissed_version') == latest:
            self._update_banner_outer.pack_forget()
            return
        self.update_banner_body_var.set(
            f'Version {latest} is available on your portal. You are running v{AGENT_VERSION}.',
        )
        if not self._update_banner_outer.winfo_ismapped():
            self._update_banner_outer.pack(fill='x', pady=(0, SECTION_GAP), before=self._pairing_banner_outer)

    def _pages_inner(self, page_id: str):
        return self._scrollables[page_id].inner

    # ------------------------------------------------------------------ token & PIN

    def _build_token_page(self) -> None:
        page = self._page_host('token')

        _, token_panel = self._section(page, 'USB signing token')

        self.active_token_var = self._tk.StringVar(value='Not set')
        self._badge_row(token_panel, 'Active for signing', self.active_token_var)

        self.token_count_var = self._tk.StringVar(value='Insert your USB token and click Refresh.')
        self._ttk.Label(
            token_panel,
            textvariable=self.token_count_var,
            style='CardMuted.TLabel',
            wraplength=640,
            justify='left',
        ).pack(anchor='w', pady=(0, 12))

        self.token_choice_var = self._tk.StringVar()
        self.token_combo = self._form_combobox(
            token_panel,
            self.token_choice_var,
            state='readonly',
        )

        actions = self._ttk.Frame(token_panel, style='Panel.TFrame')
        actions.pack(fill='x')
        self._ttk.Button(
            actions,
            text='Refresh tokens',
            style='Secondary.TButton',
            command=lambda: self._refresh_usb_tokens(background=True),
        ).pack(side='left')
        self._ttk.Button(
            actions,
            text='Use for signing',
            style='Primary.TButton',
            command=self._save_usb_token,
        ).pack(side='left', padx=(10, 0))

        _, pin_panel = self._section(page, 'PIN memory')

        self.pin_env_notice = self._ttk.Label(
            pin_panel,
            text='',
            style='BannerInfo.TLabel',
            wraplength=640,
            justify='left',
        )

        self.pin_status_detail_var = self._tk.StringVar(value='')
        self._ttk.Label(
            pin_panel,
            textvariable=self.pin_status_detail_var,
            style='CardMuted.TLabel',
            wraplength=640,
            justify='left',
        ).pack(anchor='w', pady=(0, 12))

        self.pin_enabled_var = self._tk.BooleanVar(value=True)
        self.pin_enabled_check = self._ttk.Checkbutton(
            pin_panel,
            text='Remember PIN for faster signing',
            style='Card.TCheckbutton',
            variable=self.pin_enabled_var,
            command=self._on_pin_setting_changed,
        )
        self.pin_enabled_check.pack(anchor='w', pady=(0, 10))

        hours_row = self._ttk.Frame(pin_panel, style='Panel.TFrame')
        hours_row.pack(fill='x', pady=(0, 10))
        self._ttk.Label(hours_row, text='Remember for (hours)', style='FieldLabel.TLabel', width=18).pack(side='left')
        self.pin_hours_var = self._tk.StringVar(value='6')
        self.pin_hours_entry = self._ttk.Entry(hours_row, textvariable=self.pin_hours_var, width=10, style='Form.TEntry')
        self.pin_hours_entry.pack(side='left')
        self.pin_hours_entry.bind('<KeyRelease>', lambda _event: self._on_pin_setting_changed())

        self.pin_clear_disconnect_var = self._tk.BooleanVar(value=True)
        self.pin_clear_disconnect_check = self._ttk.Checkbutton(
            pin_panel,
            text='Clear remembered PIN when the USB token is removed',
            style='Card.TCheckbutton',
            variable=self.pin_clear_disconnect_var,
            command=self._on_pin_setting_changed,
        )
        self.pin_clear_disconnect_check.pack(anchor='w', pady=(0, 10))

        self.pin_dirty_var = self._tk.StringVar(value='')
        self._ttk.Label(
            pin_panel,
            textvariable=self.pin_dirty_var,
            style='CardMuted.TLabel',
            foreground=WARNING,
        ).pack(anchor='w', pady=(0, 10))

        pin_actions = self._ttk.Frame(pin_panel, style='Panel.TFrame')
        pin_actions.pack(fill='x')
        self._ttk.Button(
            pin_actions,
            text='Clear remembered PIN',
            style='Danger.TButton',
            command=self._clear_remembered_pin,
        ).pack(side='left')

    def _set_pair_progress(self, message: str) -> None:
        text = (message or '').strip()
        self.pair_progress_var.set(text)
        if text:
            if not self.pair_progress_label.winfo_ismapped():
                self.pair_progress_label.pack(anchor='w', pady=(8, 0), before=self.paired_note)
        else:
            self.pair_progress_label.pack_forget()

    def _pin_env_locked(self) -> dict[str, bool]:
        from pkcs11_signing import pin_cache_env_locked, pin_cache_managed_by_env

        if pin_cache_managed_by_env():
            return pin_cache_env_locked()
        return {'enabled': False, 'hours': False, 'clear_on_disconnect': False}

    def _load_pin_settings(self) -> None:
        from pkcs11_signing import get_pin_cache_settings, pin_cache_status_message

        self._pin_loading = True
        settings = get_pin_cache_settings()
        self.pin_enabled_var.set(settings['enabled'])
        self.pin_hours_var.set(str(settings['hours']))
        self.pin_clear_disconnect_var.set(settings['clear_on_disconnect'])
        self.pin_status_detail_var.set(pin_cache_status_message())
        self._pin_dirty = False
        self._update_pin_dirty_label()
        self._apply_pin_env_lock()
        self._pin_loading = False

    def _apply_pin_env_lock(self) -> None:
        locked = self._pin_env_locked()
        if any(locked.values()):
            self.pin_env_notice.configure(
                text='Some PIN settings are controlled by environment variables on this PC and cannot be changed here.',
            )
            self.pin_env_notice.pack(anchor='w', pady=(0, 12))
        else:
            self.pin_env_notice.configure(text='')
            self.pin_env_notice.pack_forget()

        self.pin_enabled_check.configure(state='disabled' if locked['enabled'] else 'normal')
        self.pin_clear_disconnect_check.configure(
            state='disabled' if locked['clear_on_disconnect'] else 'normal',
        )
        hours_state = 'disabled' if locked['hours'] or not self.pin_enabled_var.get() else 'normal'
        self.pin_hours_entry.configure(state=hours_state)

    def _on_pin_setting_changed(self) -> None:
        if self._pin_loading:
            return
        self._apply_pin_env_lock()
        self._pin_dirty = True
        self._update_pin_dirty_label()
        self._debounced_pin_save()

    def _update_pin_dirty_label(self) -> None:
        self.pin_dirty_var.set('Unsaved changes — saving…' if self._pin_dirty else '')

    def _current_pin_form_values(self) -> dict:
        try:
            hours = max(0.0, float(self.pin_hours_var.get().strip() or '0'))
        except ValueError:
            hours = 0.0
        return {
            'enabled': bool(self.pin_enabled_var.get()),
            'hours': hours,
            'clear_on_disconnect': bool(self.pin_clear_disconnect_var.get()),
        }

    def _flush_pin_settings(self) -> None:
        from pkcs11_signing import save_pin_cache_settings, pin_cache_status_message

        if not self._pin_dirty:
            return
        values = self._current_pin_form_values()
        locked = self._pin_env_locked()
        try:
            save_pin_cache_settings(
                enabled=None if locked['enabled'] else values['enabled'],
                hours=None if locked['hours'] else values['hours'],
                clear_on_disconnect=None if locked['clear_on_disconnect'] else values['clear_on_disconnect'],
            )
        except Exception as exc:
            self.toast.show(f'Could not save PIN settings: {exc}', tone='error')
            return
        self._pin_dirty = False
        self._update_pin_dirty_label()
        self.pin_status_detail_var.set(pin_cache_status_message())
        self.toast.show('PIN settings saved.', tone='ok', duration_ms=2500)
        self._refresh_view()

    def _clear_remembered_pin(self) -> None:
        from pkcs11_signing import clear_session_pin, pin_cache_status_message

        if not confirm_dialog(
            self.root,
            title='Clear remembered PIN',
            message='The agent will ask for your token PIN on the next signature.',
            confirm_label='Clear PIN',
        ):
            return
        clear_session_pin()
        self.pin_status_detail_var.set(pin_cache_status_message())
        self.toast.show('Remembered PIN cleared.', tone='ok')
        self._refresh_view()

    # ------------------------------------------------------------------ pair

    def _build_pair_page(self) -> None:
        page = self._page_host('pair')

        _, portal_panel = self._section(page, 'Portal shortcuts')
        portal_actions = self._ttk.Frame(portal_panel, style='Panel.TFrame')
        portal_actions.pack(fill='x')
        self._ttk.Button(
            portal_actions,
            text='Open USB Agent page',
            style='Primary.TButton',
            command=self._open_portal_page,
        ).pack(side='left')
        self._ttk.Button(
            portal_actions,
            text='Open portal home',
            style='Secondary.TButton',
            command=self._open_portal_home,
        ).pack(side='left', padx=(10, 0))
        self._ttk.Button(
            portal_actions,
            text='Download Windows installer',
            style='Secondary.TButton',
            command=self._download_installer,
        ).pack(side='left', padx=(10, 0))

        _, self.pair_frame = self._section(page, 'Pair this device')

        self._ttk.Label(self.pair_frame, text='Portal URL', style='FieldLabel.TLabel').pack(anchor='w')
        readonly = self._readonly_box(self.pair_frame)
        readonly.pack(fill='x', pady=(6, 16))
        self.portal_url_var = self._tk.StringVar(value=self._initial_api_base() or 'Not configured')
        self._ttk.Label(
            readonly,
            textvariable=self.portal_url_var,
            style='ReadOnlyValue.TLabel',
            wraplength=580,
        ).pack(anchor='w', fill='x')

        self._ttk.Label(self.pair_frame, text='Pairing code', style='FieldLabel.TLabel').pack(anchor='w')
        self.code_var = self._tk.StringVar()
        code_entry = self._form_entry(self.pair_frame, self.code_var)
        code_entry.bind('<Return>', lambda _event: self._pair())

        self.pair_button = self._ttk.Button(
            self.pair_frame,
            text='Pair agent',
            style='Primary.TButton',
            command=self._pair,
        )
        self.pair_button.pack(anchor='w', pady=(0, 4))

        self.pair_progress_var = self._tk.StringVar(value='')
        self.pair_progress_label = self._ttk.Label(
            self.pair_frame,
            textvariable=self.pair_progress_var,
            style='CardMuted.TLabel',
            wraplength=640,
        )

        self.paired_note = self._ttk.Label(
            self.pair_frame,
            text='Generate a pairing code in the portal under USB Agent.',
            style='CardMuted.TLabel',
            wraplength=640,
            justify='left',
        )
        self.paired_note.pack(anchor='w', pady=(12, 0))

    # ------------------------------------------------------------------ origins

    def _build_origins_page(self) -> None:
        page = self._page_host('origins')

        _, self.origins_frame = self._section(page, 'Allowed browser origins')

        self._ttk.Label(
            self.origins_frame,
            text='Browsers send an Origin header when a web app calls this agent. Your paired portal is always allowed.',
            style='CardMuted.TLabel',
            wraplength=640,
            justify='left',
        ).pack(anchor='w', pady=(0, 14))

        self._ttk.Label(self.origins_frame, text='Portal origin', style='Section.TLabel').pack(anchor='w')
        portal_box = self._readonly_box(self.origins_frame)
        portal_box.pack(fill='x', pady=(6, 16))
        self.portal_origin_var = self._tk.StringVar(value='—')
        self._ttk.Label(
            portal_box,
            textvariable=self.portal_origin_var,
            style='ReadOnlyValue.TLabel',
            wraplength=580,
        ).pack(anchor='w', fill='x')

        self._ttk.Label(self.origins_frame, text='Additional origins', style='Section.TLabel').pack(anchor='w')
        self._ttk.Label(
            self.origins_frame,
            text='Add origins for ERP or internal web apps (e.g. Business Central).',
            style='CardMuted.TLabel',
            wraplength=640,
            justify='left',
        ).pack(anchor='w', pady=(4, 10))

        self.origins_empty_var = self._tk.StringVar(value='')
        self.origins_empty_label = self._ttk.Label(
            self.origins_frame,
            textvariable=self.origins_empty_var,
            style='CardMuted.TLabel',
            wraplength=640,
        )

        self.origins_listbox, self._origins_scroll, self._origins_list_wrap = self._form_listbox(
            self.origins_frame,
            height=4,
        )

        origin_entry_row = self._ttk.Frame(self.origins_frame, style='Panel.TFrame')
        origin_entry_row.pack(fill='x')
        self.origin_entry_var = self._tk.StringVar()
        origin_entry = self._ttk.Entry(origin_entry_row, textvariable=self.origin_entry_var, style='Form.TEntry')
        origin_entry.pack(side='left', fill='x', expand=True, padx=(0, 10))
        origin_entry.bind('<Return>', lambda _event: self._add_allowed_origin())
        self._ttk.Button(
            origin_entry_row,
            text='Add origin',
            style='Secondary.TButton',
            command=self._add_allowed_origin,
        ).pack(side='left')
        self._ttk.Button(
            self.origins_frame,
            text='Remove selected',
            style='Danger.TButton',
            command=self._remove_allowed_origin,
        ).pack(anchor='w', pady=(12, 0))

    # ------------------------------------------------------------------ actions

    def _build_actions_page(self) -> None:
        page = self._page_host('actions')

        _, portal_panel = self._section(page, 'Portal')
        for label, command in (
            ('Open USB Agent page in browser', self._open_portal_page),
            ('Download Windows installer', self._download_installer),
        ):
            self._ttk.Button(portal_panel, text=label, style='Secondary.TButton', command=command).pack(
                fill='x',
                pady=(0, 10),
            )

        _, device_panel = self._section(page, 'Device')
        self._ttk.Button(
            device_panel,
            text='Token & PIN settings',
            style='Secondary.TButton',
            command=lambda: self.navigate_to('token'),
        ).pack(fill='x', pady=(0, 10))
        self._ttk.Button(
            device_panel,
            text='Open config folder',
            style='Secondary.TButton',
            command=self._open_config_folder,
        ).pack(fill='x')

        _, danger_panel = self._section(page, 'Danger zone')
        self._ttk.Label(
            danger_panel,
            text='These actions affect pairing and whether the agent keeps running.',
            style='CardMuted.TLabel',
            wraplength=640,
            justify='left',
        ).pack(anchor='w', pady=(0, 12))
        self._ttk.Button(
            danger_panel,
            text='Re-pair with portal',
            style='Danger.TButton',
            command=self._unpair,
        ).pack(fill='x', pady=(0, 10))
        self._ttk.Button(
            danger_panel,
            text='Quit agent',
            style='Danger.TButton',
            command=self._quit,
        ).pack(fill='x')

    # ------------------------------------------------------------------ navigation

    def navigate_to(self, page_id: str) -> None:
        """Switch to a dashboard page (public API for tray / external callers)."""
        self._request_page(page_id)

    def _request_page(self, page_id: str) -> None:
        if page_id not in self.pages:
            return
        if page_id != self._active_page and self._pin_dirty and self._active_page == 'token':
            if not confirm_dialog(
                self.root,
                title='Unsaved PIN settings',
                message='PIN settings are still saving. Leave this page anyway?',
                confirm_label='Leave page',
            ):
                return
            self._flush_pin_settings()
        self._show_page(page_id)

    def _show_page(self, page_id: str) -> None:
        subtitles = {
            'status': 'Connection and signing readiness',
            'token': 'USB token selection and PIN memory',
            'pair': 'Connect this computer to your IG E-Sign portal',
            'origins': 'Web apps allowed to call the local agent',
            'actions': 'Shortcuts, maintenance, and advanced options',
        }
        titles = dict(NAV_ITEMS)
        self._active_page = page_id
        self.page_title.set(titles.get(page_id, 'Agent'))
        self.page_subtitle.set(subtitles.get(page_id, ''))

        for pid, button in self._nav_buttons.items():
            active = pid == page_id
            button.configure(style='NavActive.TButton' if active else 'Nav.TButton')
            self._nav_indicators[pid].configure(bg=ACCENT if active else SURFACE)

        for frame in self.pages.values():
            frame.pack_forget()
        self.pages[page_id].pack(fill='both', expand=True)

        if page_id == 'token':
            self._load_pin_settings()

    # ------------------------------------------------------------------ data helpers

    def _initial_api_base(self) -> str:
        config = load_config()
        return config.get('api_base') or read_default_api_base()

    def _portal_base_url(self) -> str:
        snap = self.state.snapshot()
        return (snap['api_base'] or load_config().get('api_base') or self._initial_api_base() or '').rstrip('/')

    def _refresh_portal_url_display(self) -> None:
        api_base = self._initial_api_base()
        self.portal_url_var.set(api_base or 'Not configured — reinstall from your IG E-Sign portal')

    def _token_scan_error_message(self) -> str:
        from pkcs11_signing import resolve_pkcs11_dll

        if resolve_pkcs11_dll() is None:
            return (
                'PKCS#11 driver not found. Install your token vendor software (eMudhra, Capricorn, etc.) '
                'or set IG_AGENT_PKCS11_DLL to the correct DLL path.'
            )
        return 'No USB token detected. Insert your token, unlock it if needed, and click Refresh.'

    def _refresh_usb_tokens(self, *, background: bool = True) -> None:
        if self._token_refresh_running:
            return

        def worker():
            from pkcs11_signing import refresh_usb_tokens, resolve_pkcs11_dll

            try:
                if resolve_pkcs11_dll() is None:
                    tokens = []
                    error = 'pkcs11_missing'
                else:
                    tokens = refresh_usb_tokens()
                    error = ''
            except Exception as exc:
                tokens = []
                error = str(exc)
            self.root.after(0, lambda: self._apply_usb_tokens(tokens, error=error))

        self._token_refresh_running = True
        self.token_count_var.set('Scanning USB tokens…')
        if background:
            threading.Thread(target=worker, daemon=True, name='ig-agent-token-scan').start()
        else:
            worker()

    def _apply_usb_tokens(self, tokens, *, error: str = '') -> None:
        from pkcs11_signing import format_token_display, match_saved_token, saved_token_display

        self._token_refresh_running = False
        self._usb_tokens = tokens

        display = saved_token_display()
        self.active_token_var.set(display or 'Not set — choose a token below')

        if error == 'pkcs11_missing':
            self.token_count_var.set(self._token_scan_error_message())
            self.token_combo['values'] = ()
            self.token_choice_var.set('')
            self._refresh_view()
            return

        if not tokens:
            message = self._token_scan_error_message()
            if error and error != 'pkcs11_missing':
                message = f'{message} ({error})'
            self.token_count_var.set(message)
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

    def _save_usb_token(self) -> None:
        from pkcs11_signing import save_token_preference

        if not self._usb_tokens:
            self.toast.show(self._token_scan_error_message(), tone='warn')
            return
        selected = self.token_choice_var.get().strip()
        token = next((item for item in self._usb_tokens if item.display_name() == selected), None)
        if token is None:
            self.toast.show('Select a token from the list.', tone='warn')
            return
        save_token_preference(
            token.slot_id,
            label=token.label,
            serial=token.serial,
            signer_name=token.signer_name,
        )
        self.toast.show(f'Using {token.display_name()} for signing.', tone='ok')
        self._refresh_view()

    def _selected_token_line(self, snap: dict) -> str:
        from pkcs11_signing import saved_token_display

        if not snap.get('token_present'):
            return 'Not detected'
        display = saved_token_display()
        if display:
            return display
        if self._usb_tokens:
            if len(self._usb_tokens) == 1:
                return f'{self._usb_tokens[0].display_name()} (not confirmed)'
            return 'Detected — choose on Token & PIN'
        return 'Detected'

    def _schedule_refresh(self) -> None:
        self._refresh_view()
        self._refresh_job = self.root.after(REFRESH_MS, self._schedule_refresh)

    def _refresh_view(self) -> None:
        from pkcs11_signing import pin_cache_status_message

        snap = self.state.snapshot()
        config = load_config()
        has_token = bool(config.get('device_token'))
        revoked = is_revoked_token_error(snap['last_error'])
        show_pairing = not has_token or revoked
        tenant = config.get('tenant_name') or '—'

        if show_pairing and not has_token:
            headline = 'Not paired'
            headline_style = 'StatusWarn.TLabel'
            self.portal_var.set('Not connected')
            self.token_var.set('—')
            self._set_sidebar_status('Not paired', tone='warn')
        elif show_pairing and revoked:
            headline = 'Device revoked'
            headline_style = 'StatusBad.TLabel'
            self.portal_var.set(config.get('api_base') or snap['api_base'] or '—')
            self.token_var.set('—')
            self._set_sidebar_status('Revoked — re-pair', tone='bad')
        elif snap['portal_connected'] and has_token:
            headline = 'Ready to sign'
            headline_style = 'StatusOk.TLabel'
            self.portal_var.set(config.get('api_base') or snap['api_base'] or '—')
            self.token_var.set(self._selected_token_line(snap))
            self._set_sidebar_status('Connected', tone='ok')
        else:
            detail = humanize_agent_error(snap['last_error'])
            headline = f'Offline — {detail}'
            headline_style = 'StatusWarn.TLabel'
            self.portal_var.set(config.get('api_base') or snap['api_base'] or '—')
            self.token_var.set(self._selected_token_line(snap))
            self._set_sidebar_status('Offline', tone='warn')

        self.status_headline.set(headline)
        self.status_headline_label.configure(style=headline_style)
        self.tenant_var.set(tenant)
        self.pin_status_var.set(pin_cache_status_message())
        self.port_var.set(f'127.0.0.1:{snap["port"]}')

        if show_pairing and not has_token:
            if not self._pairing_banner_outer.winfo_ismapped():
                self._pairing_banner_outer.pack(fill='x', pady=(0, SECTION_GAP), before=self._status_section)
        else:
            self._pairing_banner_outer.pack_forget()

        self._update_welcome_banner()
        self._update_version_banner()

        display = None
        try:
            from pkcs11_signing import saved_token_display

            display = saved_token_display()
        except Exception:
            pass
        if display:
            self.active_token_var.set(display)
        elif hasattr(self, 'active_token_var'):
            self.active_token_var.set('Not set — choose a token below')

        if has_token and snap.get('token_present') is not False:
            self.state.update(paired=True, token_present=token_present())
        elif not has_token:
            self.state.update(paired=False, portal_connected=False, last_error='')

        self._refresh_origins_view()
        self._refresh_portal_url_display()

    def _refresh_origins_view(self) -> None:
        config = load_config()
        portal = portal_origin_from_config(config)
        if portal:
            self.portal_origin_var.set(portal)
        else:
            self.portal_origin_var.set('— pair the agent first')

        extras = list_extra_allowed_origins(config)
        self.origins_listbox.delete(0, 'end')
        for origin in extras:
            self.origins_listbox.insert('end', origin)

        if extras:
            self.origins_empty_var.set('')
            self.origins_empty_label.pack_forget()
        else:
            self.origins_empty_var.set('No additional origins yet. Add one for ERP or custom web apps.')
            if not self.origins_empty_label.winfo_ismapped():
                self.origins_empty_label.pack(anchor='w', pady=(0, 8), before=self._origins_list_wrap)

        visible_rows = max(3, min(8, len(extras) if extras else 3))
        self.origins_listbox.configure(height=visible_rows)
        if len(extras) > visible_rows:
            self._origins_scroll.pack(side='right', fill='y')
        else:
            self._origins_scroll.pack_forget()

        scroll = self._scrollables.get('origins')
        if scroll is not None:
            scroll._update_scrollbar_visibility()

    def _set_sidebar_status(self, text: str, *, tone: str = 'muted') -> None:
        styles = {
            'ok': 'StatusOk.TLabel',
            'warn': 'StatusWarn.TLabel',
            'bad': 'StatusBad.TLabel',
            'muted': 'SidebarMuted.TLabel',
        }
        self.sidebar_status.set(text)
        self.sidebar_status_label.configure(style=styles.get(tone, 'SidebarMuted.TLabel'))

    # ------------------------------------------------------------------ origins actions

    def _add_allowed_origin(self) -> None:
        origin = self.origin_entry_var.get().strip()
        if not origin:
            self.toast.show('Enter an origin URL to add.', tone='warn')
            return
        try:
            add_allowed_origin(origin)
        except OriginValidationError as exc:
            self.toast.show(str(exc), tone='error')
            return
        normalized = normalize_origin(origin)
        self.origin_entry_var.set('')
        self._refresh_origins_view()
        self.toast.show(f'Added {normalized}', tone='ok')

    def _remove_allowed_origin(self) -> None:
        selection = self.origins_listbox.curselection()
        if not selection:
            self.toast.show('Select an origin to remove.', tone='warn')
            return
        origin = self.origins_listbox.get(selection[0])
        if not confirm_dialog(
            self.root,
            title='Remove allowed origin',
            message=f'Remove {origin} from the allowed list?',
            confirm_label='Remove',
        ):
            return
        remove_allowed_origin(origin)
        self._refresh_origins_view()
        self.toast.show(f'Removed {origin}', tone='ok')

    # ------------------------------------------------------------------ pair / portal

    def _pair(self) -> None:
        if self._pair_running:
            return
        api_base = self._initial_api_base().strip()
        code = self.code_var.get().strip()
        if not api_base:
            self.toast.show(
                'Portal URL is not configured. Download and install the agent from your IG E-Sign portal.',
                tone='error',
            )
            return
        if not code:
            self.toast.show('Enter the pairing code from the USB Agent page.', tone='warn')
            return

        self._pair_running = True
        self.pair_button.configure(state='disabled')
        self._set_pair_progress('Pairing with portal…')

        def worker():
            ok, message, tenant = self.on_pair(api_base, code)
            self.root.after(0, lambda: self._finish_pair(ok, message, tenant, api_base))

        threading.Thread(target=worker, daemon=True, name='ig-agent-pair').start()

    def _finish_pair(self, ok: bool, message: str, tenant: str, api_base: str) -> None:
        self._pair_running = False
        self.pair_button.configure(state='normal')
        self._set_pair_progress('')

        if not ok:
            self.toast.show(humanize_agent_error(message), tone='error')
            return

        config = load_config()
        if tenant:
            config['tenant_name'] = tenant
            save_config(config)

        self.state.update(
            paired=True,
            api_base=config.get('api_base', api_base.rstrip('/')),
            portal_connected=True,
            last_error='',
        )
        self.code_var.set('')
        label = tenant or config.get('tenant_name') or 'your portal'
        self.toast.show(f'Connected to {label}.', tone='ok')
        self.navigate_to('status')
        self._refresh_view()

    def _unpair(self) -> None:
        if not confirm_dialog(
            self.root,
            title='Re-pair with portal',
            message='Clear local pairing? You will need a new code from the USB Agent page.',
            confirm_label='Clear pairing',
        ):
            return
        clear_pairing()
        self.code_var.set('')
        self._refresh_portal_url_display()
        self.toast.show('Pairing cleared. Enter a new code on Pair portal.', tone='info')
        self.navigate_to('pair')
        self._refresh_view()

    def _open_portal_page(self) -> None:
        base = self._portal_base_url()
        if not base:
            self.toast.show('Pair the agent first or reinstall from your portal.', tone='warn')
            return
        webbrowser.open(f'{base}/dashboard/agent/')

    def _open_portal_home(self) -> None:
        base = self._portal_base_url()
        if not base:
            self.toast.show('Portal URL is not configured.', tone='warn')
            return
        webbrowser.open(f'{base}/dashboard/')

    def _download_installer(self) -> None:
        base = self._portal_base_url()
        if not base:
            self.toast.show('Portal URL is not configured.', tone='warn')
            return
        webbrowser.open(f'{base}/dashboard/agent/download/')

    def _open_config_folder(self) -> None:
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

    # ------------------------------------------------------------------ window lifecycle

    def hide_to_tray(self) -> None:
        config = load_config()
        if not config.get('ui_close_hint_shown'):
            config['ui_close_hint_shown'] = True
            save_config(config)
            if sys.platform == 'win32':
                try:
                    import ctypes

                    ctypes.windll.user32.MessageBoxW(
                        0,
                        'Closing this window keeps the agent running in the system tray near the clock.\n\n'
                        'Right-click the tray icon to reopen this window or quit the agent.',
                        'IG E-Sign Agent',
                        0x40,
                    )
                except Exception:
                    self.toast.show(
                        'Agent keeps running in the system tray. Right-click the tray icon to reopen.',
                        tone='info',
                        duration_ms=6000,
                    )
                    self.root.after(6200, self._withdraw_to_tray)
                    return
        self._withdraw_to_tray()

    def _withdraw_to_tray(self) -> None:
        self._hidden = True
        self.root.withdraw()

    def show(self) -> None:
        self._hidden = False
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(200, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()
        self._refresh_view()

    def _quit(self) -> None:
        if not confirm_dialog(
            self.root,
            title='Quit agent',
            message='Stop the IG E-Sign Agent? Browser signing will not work until you start it again.',
            confirm_label='Quit',
        ):
            return
        if self._refresh_job:
            self.root.after_cancel(self._refresh_job)
        from pkcs11_signing import unregister_main_ui_root

        unregister_main_ui_root()
        if self.on_quit:
            self.on_quit()

    def run(self) -> None:
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

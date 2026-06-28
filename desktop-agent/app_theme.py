"""Portal-aligned theme tokens and ttk styling for the desktop agent (light mode)."""

from __future__ import annotations

# Incite Gravity / IG E-Sign light theme (matches portal data-theme='light')
BG = '#f5f6fa'
SURFACE = '#ffffff'
SURFACE_RAISED = '#ffffff'
ACCENT = '#ff6600'
ACCENT_HOVER = '#e55a00'
ACCENT_SOFT = '#fff4eb'
TEXT_PRIMARY = '#020626'
TEXT_SECONDARY = '#5c6078'
BORDER = '#d8dbe8'
SUCCESS = '#059669'
WARNING = '#d97706'
DANGER = '#da291c'
INFO_BG = '#eff6ff'
INFO_FG = '#1d4ed8'

SIDEBAR_WIDTH = 232
FONT = 'Segoe UI'
MONO = 'Consolas'
FOCUS_COLOR = ACCENT
SECTION_GAP = 20


def configure_styles(root) -> None:
    from tkinter import ttk

    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except Exception:
        pass

    root.configure(bg=BG)

    style.configure('.', background=BG, foreground=TEXT_PRIMARY, font=(FONT, 10))
    style.configure('TFrame', background=BG)
    style.configure('Card.TFrame', background=SURFACE, relief='flat')
    style.configure('Panel.TFrame', background=SURFACE, relief='flat')
    style.configure('Sidebar.TFrame', background=SURFACE)
    style.configure('SidebarBrand.TFrame', background=SURFACE)
    style.configure('NavRow.TFrame', background=SURFACE)
    style.configure('Main.TFrame', background=BG)

    style.configure('TLabel', background=BG, foreground=TEXT_PRIMARY, font=(FONT, 10))
    style.configure('Muted.TLabel', foreground=TEXT_SECONDARY, background=BG)
    style.configure('Sidebar.TLabel', background=SURFACE, foreground=TEXT_PRIMARY)
    style.configure('SidebarMuted.TLabel', background=SURFACE, foreground=TEXT_SECONDARY)
    style.configure('Card.TLabel', background=SURFACE, foreground=TEXT_PRIMARY)
    style.configure('CardMuted.TLabel', background=SURFACE, foreground=TEXT_SECONDARY)
    style.configure('Title.TLabel', font=(FONT, 20, 'bold'), background=BG, foreground=TEXT_PRIMARY)
    style.configure('Subtitle.TLabel', font=(FONT, 10), foreground=TEXT_SECONDARY, background=BG)
    style.configure(
        'SectionHeading.TLabel',
        background=BG,
        foreground=TEXT_SECONDARY,
        font=(FONT, 9, 'bold'),
    )
    style.configure(
        'Section.TLabel',
        background=SURFACE,
        foreground=TEXT_SECONDARY,
        font=(FONT, 9, 'bold'),
    )
    style.configure('FieldLabel.TLabel', background=SURFACE, foreground=TEXT_SECONDARY, font=(FONT, 9))
    style.configure('FieldValue.TLabel', background=SURFACE, foreground=TEXT_PRIMARY, font=(FONT, 10))
    style.configure('PageFooter.TLabel', background=BG, foreground=TEXT_SECONDARY, font=(FONT, 9))

    style.configure(
        'TEntry',
        fieldbackground=SURFACE,
        foreground=TEXT_PRIMARY,
        insertcolor=TEXT_PRIMARY,
        bordercolor=BORDER,
    )
    style.configure(
        'TCombobox',
        fieldbackground=SURFACE,
        foreground=TEXT_PRIMARY,
        background=SURFACE,
        arrowcolor=TEXT_SECONDARY,
        bordercolor=BORDER,
    )

    _button_focus = {'focusthickness': 2, 'focuscolor': FOCUS_COLOR}

    style.configure(
        'Primary.TButton',
        background=ACCENT,
        foreground='#ffffff',
        borderwidth=0,
        padding=(14, 10),
        font=(FONT, 10, 'bold'),
        **_button_focus,
    )
    style.map(
        'Primary.TButton',
        background=[('active', ACCENT_HOVER), ('pressed', ACCENT_HOVER)],
        foreground=[('disabled', TEXT_SECONDARY)],
    )

    style.configure(
        'Secondary.TButton',
        background=SURFACE,
        foreground=TEXT_PRIMARY,
        bordercolor=BORDER,
        borderwidth=1,
        padding=(12, 8),
        font=(FONT, 10),
        **_button_focus,
    )
    style.map(
        'Secondary.TButton',
        background=[('active', BG), ('pressed', BG)],
    )

    style.configure(
        'Danger.TButton',
        background=SURFACE,
        foreground=DANGER,
        bordercolor=DANGER,
        borderwidth=1,
        padding=(12, 8),
        font=(FONT, 10, 'bold'),
        **_button_focus,
    )
    style.map(
        'Danger.TButton',
        background=[('active', '#fef2f2'), ('pressed', '#fef2f2')],
    )

    style.configure(
        'Nav.TButton',
        background=SURFACE,
        foreground=TEXT_SECONDARY,
        borderwidth=0,
        anchor='w',
        padding=(12, 10),
        font=(FONT, 10),
        focuscolor=ACCENT_SOFT,
        focusthickness=2,
    )
    style.map(
        'Nav.TButton',
        background=[('active', BG)],
        foreground=[('active', TEXT_PRIMARY)],
    )
    style.configure(
        'NavActive.TButton',
        background=ACCENT_SOFT,
        foreground=ACCENT,
        borderwidth=0,
        anchor='w',
        padding=(12, 10),
        font=(FONT, 10, 'bold'),
        focuscolor=ACCENT_SOFT,
        focusthickness=2,
    )

    style.configure(
        'Card.TCheckbutton',
        background=SURFACE,
        foreground=TEXT_PRIMARY,
        focuscolor=ACCENT_SOFT,
        focusthickness=2,
    )
    style.map(
        'Card.TCheckbutton',
        background=[('active', SURFACE), ('disabled', SURFACE)],
        foreground=[('disabled', TEXT_SECONDARY)],
    )

    style.configure('ReadOnlyValue.TLabel', background=BG, foreground=TEXT_PRIMARY, font=(MONO, 10), padding=(10, 8))
    style.configure('HighlightBox.TFrame', background=BG, relief='solid', borderwidth=1, bordercolor=BORDER)
    style.configure('StatusOk.TLabel', background=SURFACE, foreground=SUCCESS, font=(FONT, 14, 'bold'))
    style.configure('StatusWarn.TLabel', background=SURFACE, foreground=WARNING, font=(FONT, 14, 'bold'))
    style.configure('StatusBad.TLabel', background=SURFACE, foreground=DANGER, font=(FONT, 14, 'bold'))
    style.configure('StatusMuted.TLabel', background=SURFACE, foreground=TEXT_SECONDARY, font=(FONT, 10))
    style.configure('BannerInfo.TLabel', background=INFO_BG, foreground=INFO_FG, font=(FONT, 10), padding=(12, 10))
    style.configure('BannerWarn.TLabel', background='#fffbeb', foreground=WARNING, font=(FONT, 10), padding=(12, 10))

    style.configure('Vertical.TScrollbar', background=SURFACE, troughcolor=BG, bordercolor=BORDER)
    style.configure('Horizontal.TSeparator', background=BORDER)

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

SIDEBAR_WIDTH = 232
FONT = 'Segoe UI'
MONO = 'Consolas'


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
    style.configure('Sidebar.TFrame', background=SURFACE)
    style.configure('SidebarBrand.TFrame', background=SURFACE)

    style.configure(
        'Card.TLabelframe',
        background=SURFACE,
        foreground=TEXT_PRIMARY,
        bordercolor=BORDER,
        relief='solid',
        borderwidth=1,
    )
    style.configure(
        'Card.TLabelframe.Label',
        background=SURFACE,
        foreground=TEXT_PRIMARY,
        font=(FONT, 10, 'bold'),
    )

    style.configure('TLabel', background=BG, foreground=TEXT_PRIMARY, font=(FONT, 10))
    style.configure('Muted.TLabel', foreground=TEXT_SECONDARY, background=BG)
    style.configure('Sidebar.TLabel', background=SURFACE, foreground=TEXT_PRIMARY)
    style.configure('SidebarMuted.TLabel', background=SURFACE, foreground=TEXT_SECONDARY)
    style.configure('Card.TLabel', background=SURFACE, foreground=TEXT_PRIMARY)
    style.configure('CardMuted.TLabel', background=SURFACE, foreground=TEXT_SECONDARY)
    style.configure('Title.TLabel', font=(FONT, 18, 'bold'), background=BG, foreground=TEXT_PRIMARY)
    style.configure('Subtitle.TLabel', font=(FONT, 9), foreground=TEXT_SECONDARY, background=BG)

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

    style.configure(
        'Primary.TButton',
        background=ACCENT,
        foreground='#ffffff',
        borderwidth=0,
        focusthickness=0,
        padding=(14, 10),
        font=(FONT, 10, 'bold'),
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
        focusthickness=0,
        padding=(12, 8),
        font=(FONT, 10),
    )
    style.map(
        'Secondary.TButton',
        background=[('active', BG), ('pressed', BG)],
    )

    style.configure(
        'Nav.TButton',
        background=SURFACE,
        foreground=TEXT_SECONDARY,
        borderwidth=0,
        anchor='w',
        padding=(14, 10),
        font=(FONT, 10, 'bold'),
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
        padding=(14, 10),
        font=(FONT, 10, 'bold'),
    )

    style.configure('Vertical.TScrollbar', background=SURFACE, troughcolor=BG, bordercolor=BORDER)

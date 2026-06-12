"""Minimal Django settings for the desktop agent (signing only, no SaaS DB)."""

import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = Path(sys._MEIPASS)
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = BASE_DIR

SECRET_KEY = 'ig-esign-agent-build-only'
DEBUG = False
USE_TZ = True
INSTALLED_APPS = []
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

SIGNATURE_ANCHOR_TEXT = 'Authorised Signatory'
SIGNATURE_ICON = BUNDLE_DIR / 'signPdf' / 'assets' / 'green-tick.png'
SIGNATURE_BOX_MIN_WIDTH = 118
SIGNATURE_BOX_HEIGHT = 64
SIGNATURE_FONT_SIZE = 8
SIGNATURE_BOX_RIGHT_PADDING = 28
SIGNATURE_BOX_SHIFT_RIGHT = 15
SIGNATURE_BOX_GAP_ABOVE_LABEL = 2
SIGNATURE_BOX_SHIFT_DOWN_FITZ = 8
SIGNATURE_BOX_PAGE_MARGIN = 5
SIGNATURE_ICON_DISPLAY_WIDTH = 60
SIGNATURE_ICON_OVERLAP_INSET = 20
SIGNATURE_ICON_PADDING = 2

# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DSCApi.settings')

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs, collect_submodules

project_root = Path(SPECPATH).resolve().parents[1]

block_cipher = None

hiddenimports = collect_submodules('signPdf') + collect_submodules('DSCApi')
hiddenimports += [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'endesive.pdf.cms',
    'endesive.pdf.PyPDF2_annotate',
    'fitz',
    'PIL',
    'cryptography.hazmat.backends.openssl',
]

datas = [
    (str(project_root / 'signPdf' / 'assets'), 'signPdf/assets'),
    (str(project_root / 'certs' / '.gitkeep'), 'certs'),
]
binaries = collect_dynamic_libs('fitz')

for package in ('django', 'rest_framework', 'endesive'):
    pkg_datas, pkg_hidden, pkg_binaries = collect_all(package)
    datas += pkg_datas
    hiddenimports += [item for item in pkg_hidden if isinstance(item, str)]
    binaries += pkg_binaries

hiddenimports = sorted(set(hiddenimports))

a = Analysis(
    [str(project_root / 'build' / 'windows' / 'launcher.py')],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DSCAPI-PFX',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DSCAPI-PFX',
)

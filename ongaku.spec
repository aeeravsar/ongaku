# -*- mode: python ; coding: utf-8 -*-
import sys
import platform

block_cipher = None

# Platform-specific binaries and data
binaries = []
datas = []

# Don't bundle VLC - require it to be installed on the system
# This makes the executable smaller and more reliable

a = Analysis(
    ['ongaku.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.downloader',
        'yt_dlp.postprocessor',
        'vlc',
        'curses',
        'curses.panel',
        'curses.textpad',
        'curses.ascii',
        'platform',
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ongaku',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console=True for terminal app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon='ongaku.ico' if you have an icon file
)
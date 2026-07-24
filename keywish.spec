# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for KeyWish GUI

block_cipher = None

a = Analysis(
    ['gui.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('config/example_mappings.json', 'config'),
    ],
    hiddenimports=[
        'keymap',
        'keymap.config',
        'keymap.keys',
        'keymap.hook',
        'keymap.engine',
        'keymap.actions',
        'keymap.service',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assembles=False,
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
    name='KeyWish',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

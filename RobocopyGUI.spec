# -*- mode: python ; coding: utf-8 -*-
import os
import qtawesome

# Die App nutzt nur das FontAwesome5-Solid-Iconset (Präfix "fa5s.") aus
# qtawesome. Statt aller mitgelieferten Icon-Fonts (~6 MB) wird gezielt nur
# dieses eine Font-Paar in die exe eingebettet, um sie schlank zu halten.
_qta_fonts_dir = os.path.join(os.path.dirname(qtawesome.__file__), 'fonts')
_qta_datas = [
    (os.path.join(_qta_fonts_dir, f), 'qtawesome/fonts')
    for f in os.listdir(_qta_fonts_dir)
    if f.startswith('fontawesome5-solid')
]

a = Analysis(
    ['RobocopyGUI.py'],
    pathex=[],
    binaries=[],
    datas=[('logo.png', '.')] + _qta_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RobocopyGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['RobocopyGUI.ico'],
)

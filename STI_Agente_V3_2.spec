# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['agente.py'], pathex=[], binaries=[], datas=[],
    hiddenimports=['win32print', 'win32ts'], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name='STI_Agente_V3_2',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, disable_windowed_traceback=False,
)

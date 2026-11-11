# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).resolve().parent
key = PROJECT_ROOT / 'sti/comum/release-public-key.pem'
a = Analysis([str(PROJECT_ROOT / 'agente.py')], pathex=[str(PROJECT_ROOT)],
    binaries=[], datas=[(str(key), 'sti/comum')], hiddenimports=['win32print', 'win32ts'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='STI_Agente',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False)

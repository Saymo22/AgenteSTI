# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).resolve().parent
resources = PROJECT_ROOT / 'build/release-resources'
a = Analysis([str(PROJECT_ROOT / 'packaging/instalador.py')], pathex=[str(PROJECT_ROOT)], binaries=[],
    datas=[(str(PROJECT_ROOT / 'dist/STI_Agente.exe'), 'resources'),
           (str(resources / 'setup-info.json'), 'resources'),
           (str(PROJECT_ROOT / 'sti/comum/release-public-key.pem'), 'sti/comum')],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='STI_Agente_Setup',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False)

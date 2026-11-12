# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

PROJECT_ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
from sti.comum.versao import AGENT_VERSION
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct
version_info = VSVersionInfo(ffi=FixedFileInfo(filevers=tuple(map(int, AGENT_VERSION.split('.'))) + (0,),
    prodvers=tuple(map(int, AGENT_VERSION.split('.'))) + (0,), mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName', 'STI'),
        StringStruct('FileDescription', 'STI Agente de inventário'), StringStruct('ProductName', 'STI Agente'),
        StringStruct('FileVersion', AGENT_VERSION), StringStruct('ProductVersion', AGENT_VERSION),
        StringStruct('OriginalFilename', 'STI_Agente.exe')])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])
key = PROJECT_ROOT / 'sti/comum/release-public-key.pem'
a = Analysis([str(PROJECT_ROOT / 'agente.py')], pathex=[str(PROJECT_ROOT)],
    binaries=[], datas=[(str(key), 'sti/comum')], hiddenimports=['win32print', 'win32ts'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='STI_Agente',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, version=version_info, disable_windowed_traceback=False)

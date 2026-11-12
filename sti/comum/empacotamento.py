"""Caminhos de execução compartilhados entre fonte, PyInstaller e Nuitka."""
import sys
from pathlib import Path


def is_bundled():
    return bool(getattr(sys, 'frozen', False) or '__compiled__' in globals())


def executable_path():
    """No Nuitka onefile, argv[0] identifica o arquivo original, não o extraído."""
    return Path(sys.argv[0] if '__compiled__' in globals() else sys.executable).resolve()


def resource_directory(module_file):
    """Dados junto ao módulo principal ou extraídos pelo PyInstaller."""
    return Path(getattr(sys, '_MEIPASS', Path(module_file).resolve().parent))

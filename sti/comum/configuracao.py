"""Configuração externa compartilhada pelo servidor e pelo agente empacotado."""
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PROJECT_ROOT
CONFIG_FILE = Path(os.environ.get("STI_CONFIG_FILE", str(BASE_DIR / "sti-config.json")))
if CONFIG_FILE.exists():
    with CONFIG_FILE.open(encoding="utf-8-sig") as stream:
        SETTINGS = json.load(stream)
    if not isinstance(SETTINGS, dict):
        raise ValueError("sti-config.json deve conter um objeto JSON.")
else:
    SETTINGS = {}


def setting(name, default=""):
    value = os.environ.get(name, SETTINGS.get(name, default))
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def positive_int(name, default, minimum=1, maximum=86400):
    value = int(setting(name, default))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} deve estar entre {minimum} e {maximum}.")
    return value

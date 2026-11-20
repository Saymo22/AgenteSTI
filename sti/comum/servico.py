"""Nomes e caminhos do serviço; este módulo não carrega a configuração."""
import os
from pathlib import Path

SERVICE_NAME = 'STIAgente'
SERVICE_DISPLAY_NAME = 'STI Agente de Monitoramento'
SERVICE_PROTOCOL = 3


def data_dir():
    # Diretório independente da pasta STI antiga, que podia pertencer a um usuário.
    return Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'STIService'


def service_mode():
    return os.environ.get('STI_SERVICE') == '1'


def prepare_environment():
    root = data_dir()
    os.environ['STI_SERVICE'] = '1'
    os.environ['STI_CONFIG_FILE'] = str(root / 'sti-config.json')
    os.environ['STI_IDENTITY_FILE'] = str(root / 'identity.db')

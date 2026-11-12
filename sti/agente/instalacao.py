"""Configuração preservada pelo instalador MSI."""
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

logger = logging.getLogger("STI_INSTALL")
CONFIG_KEYS = {'AGENT_INTERVAL', 'STI_USE_HTTPS', 'STI_IDENTITY_FILE', 'RETRY_INTERVAL', 'STI_SERVER_PORT', 'STI_SERVER_IP', 'STI_ALLOW_POWER_COMMANDS', 'STI_AGENT_TOKEN'}

def default_install_root():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'STI' / 'Agent'

def configure_install_logging():
    path = default_install_root().parent / 'logs' / 'instalador.log'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not logger.handlers:
        handler = RotatingFileHandler(path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return path

def validate_config(config):
    if not isinstance(config, dict) or config.get('STI_ADMIN_PASSWORD') or config.get('STI_SECRET_KEY'):
        raise ValueError('Use a configuração do agente, preparada a partir de agent-config.json.')
    clean = {key: value for key, value in config.items() if key in CONFIG_KEYS}
    host = clean.get('STI_SERVER_IP', '')
    token = clean.get('STI_AGENT_TOKEN', '')
    port = clean.get('STI_SERVER_PORT', 5000)
    if not isinstance(host, str) or not host.strip() or any(c in host for c in '/\\?#@ \r\n\t'):
        raise ValueError('Informe o IP ou nome DNS do servidor, sem protocolo ou caminho.')
    if not isinstance(token, str) or not token.strip() or len(token) > 512 or any(ord(c) < 32 for c in token):
        raise ValueError('Informe o token utilizado pelo servidor.')
    try:
        port = int(port)
    except (ValueError, TypeError):
        raise ValueError('Porta inválida.') from None
    if not 1 <= port <= 65535:
        raise ValueError('Porta inválida.')
    for key in ('STI_USE_HTTPS', 'STI_ALLOW_POWER_COMMANDS'):
        if isinstance(clean.get(key), str) and clean[key].strip().lower() in ('true', 'false'):
            clean[key] = clean[key].strip().lower() == 'true'
        if key in clean and not isinstance(clean[key], bool):
            raise ValueError(f'{key} deve ser true ou false.')
    clean.update(STI_SERVER_IP=host.strip(), STI_SERVER_PORT=port, STI_AGENT_TOKEN=token.strip())
    return clean

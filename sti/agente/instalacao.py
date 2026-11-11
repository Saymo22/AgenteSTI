"""Instalação Windows por usuário e operações usadas pelo atualizador."""
import contextlib
import ctypes
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psutil
from sti.comum.releases import AGENT_FILENAME, atomic_json, read_json, version_tuple

PRODUCT = 'AgenteSTI'
logger = logging.getLogger('STI_INSTALL')
CONFIG_KEYS = {'STI_SERVER_IP', 'STI_SERVER_PORT', 'STI_AGENT_TOKEN', 'STI_USE_HTTPS',
               'STI_ALLOW_POWER_COMMANDS', 'STI_IDENTITY_FILE', 'AGENT_INTERVAL', 'RETRY_INTERVAL'}


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


def acknowledge_installation():
    path = os.environ.pop('STI_INSTALL_READY_FILE', None)
    nonce = os.environ.pop('STI_INSTALL_READY_NONCE', None)
    if path and nonce:
        from sti.comum.versao import AGENT_VERSION
        atomic_json(path, {'nonce': nonce, 'version': AGENT_VERSION})


def confirm_agent_start(root, version, timeout=45):
    ready = Path(root) / ('install-ready-' + uuid.uuid4().hex + '.json')
    nonce = str(uuid.uuid4())
    process = launch_agent(root, {'STI_INSTALL_READY_FILE': str(ready), 'STI_INSTALL_READY_NONCE': nonce})
    logger.info('Agente iniciado; aguardando inicialização local. PID=%s', process.pid)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('O agente encerrou durante a inicialização. Consulte os logs do agente e do Endpoint.')
            report = read_json(ready, {})
            if report.get('nonce') == nonce and report.get('version') == version:
                time.sleep(1)
                if process.poll() is not None:
                    raise RuntimeError('O agente encerrou após inicializar. Consulte os logs do agente e do Endpoint.')
                logger.info('Inicialização local confirmada para a versão %s.', version)
                return
            time.sleep(.2)
        raise RuntimeError('O agente não confirmou a inicialização local no prazo. Consulte os logs do agente e do Endpoint.')
    finally:
        ready.unlink(missing_ok=True)


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


def installation_marker(root):
    root = Path(root).resolve()
    marker = read_json(root / 'installation.json', {})
    if not isinstance(marker, dict) or marker.get('product') != PRODUCT or marker.get('root') != str(root):
        raise ValueError('Instalação do agente não reconhecida.')
    uuid.UUID(marker['install_id'])
    return marker


@contextlib.contextmanager
def installation_lock(root):
    if sys.platform != 'win32':
        yield
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    key = hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()[:24]
    handle = kernel.CreateMutexW(None, False, 'Local\\STI_Install_' + key)
    if not handle:
        raise OSError('Não foi possível bloquear a instalação.')
    acquired = kernel.WaitForSingleObject(handle, 0) in (0, 0x80)
    try:
        if not acquired:
            raise RuntimeError('Uma instalação ou atualização já está em andamento.')
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def replace_retry(source, destination, timeout=45):
    deadline = time.monotonic() + timeout
    while True:
        try:
            Path(source).replace(destination)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.5)


def launch_agent(root, extra_env=None, config_file=None):
    root = Path(root).resolve()
    env = {**os.environ, 'STI_CONFIG_FILE': str(config_file or root / 'sti-config.json')}
    env.pop('STI_UPDATE_HEALTH_FILE', None)
    env.pop('STI_UPDATE_HEALTH_NONCE', None)
    env.pop('STI_INSTALL_READY_FILE', None)
    env.pop('STI_INSTALL_READY_NONCE', None)
    env.update(extra_env or {})
    return subprocess.Popen([str(root / AGENT_FILENAME)], cwd=root, env=env,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def stop_installed_agent(root, include_legacy=False):
    executable = (Path(root).resolve() / AGENT_FILENAME)
    matching = []
    owner = psutil.Process().username()
    legacy_names = {'sti_agente_v3.exe', 'sti_agente_v3_1.exe', 'sti_agente_v3_2.exe', 'sti_agente_v3_3.exe'}
    for process in psutil.process_iter(['pid', 'exe']):
        try:
            path = Path(process.info['exe']).resolve() if process.info['exe'] else None
            same_installation = path == executable and process.username() == owner
            # Nome sozinho não comprova a origem de uma instalação portátil antiga.
            legacy = include_legacy and path and path.name.casefold() in legacy_names and process.username() == owner
            if legacy and not same_installation:
                raise RuntimeError('Feche manualmente o agente antigo antes de instalar: ' + str(path))
            if process.pid != os.getpid() and same_installation:
                matching.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    for process in reversed(matching):
        try:
            logger.info('Encerrando processo da instalação reconhecida. PID=%s', process.pid)
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(matching, timeout=15)
    if alive:
        raise RuntimeError('Não foi possível encerrar o agente instalado. Feche-o e tente novamente.')


def register_windows(root, version, startup):
    import winreg
    root = Path(root).resolve()
    command = subprocess.list2cmdline([str(root / AGENT_FILENAME)])
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if startup:
            winreg.SetValueEx(key, PRODUCT, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, PRODUCT)
            except FileNotFoundError:
                pass
    path = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\AgenteSTI'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        values = {'DisplayName': 'STI Agente', 'DisplayVersion': version, 'Publisher': 'STI',
                  'InstallLocation': str(root),
                  'UninstallString': subprocess.list2cmdline([str(root / 'STI_Agente_Setup.exe'), '--uninstall', '--target', str(root)])}
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name in ('NoModify', 'NoRepair'):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)


def install_agent(payload, root, version, config, startup=True, launch=True, setup_source=None, register=True):
    configure_install_logging()
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    logger.info('Preparando instalação da versão %s em %s.', version, root)
    with installation_lock(root):
        old_config = read_json(root / 'sti-config.json', {})
        merged_config = validate_config({**old_config, **config})
        marker = read_json(root / 'installation.json', {})
        if marker:
            installation_marker(root)
        if marker.get('version') and version_tuple(marker['version']) > version_tuple(version):
            raise ValueError('A versão instalada é mais recente. Utilize o instalador atual.')
        executable = root / AGENT_FILENAME
        backup = root / 'previous-agent.exe'
        had_agent = executable.exists()
        incoming = root / 'incoming-agent.exe'
        logger.info('Copiando o executável para preparação.')
        shutil.copyfile(payload, incoming)
        logger.info('Verificando processos antes da substituição.')
        try:
            stop_installed_agent(root, include_legacy=True)
        except Exception:
            logger.exception('Preparação interrompida antes de substituir o executável.')
            incoming.unlink(missing_ok=True)
            raise
        moved_backup = False
        installed_new = False
        try:
            if had_agent:
                replace_retry(executable, backup)
                moved_backup = True
            replace_retry(incoming, executable)
            installed_new = True
            logger.info('Executável instalado; salvando configuração e identificação da instalação.')
            atomic_json(root / 'sti-config.json', merged_config)
            atomic_json(root / 'installation.json', {'product': PRODUCT, 'root': str(root),
                        'install_id': marker.get('install_id') or str(uuid.uuid4()), 'version': version,
                        'startup': startup, 'registered': register})
            if setup_source:
                logger.info('Preparando desinstalador local.')
                destination = root / 'STI_Agente_Setup.exe'
                if Path(setup_source).resolve() != destination:
                    shutil.copyfile(setup_source, destination)
            if register:
                logger.info('Registrando aplicativo e opção de inicialização no Windows. startup=%s', startup)
                register_windows(root, version, startup)
        except Exception:
            logger.exception('Falha durante instalação; restaurando os arquivos anteriores.')
            if installed_new:
                executable.unlink(missing_ok=True)
            if moved_backup:
                replace_retry(backup, executable)
            if old_config:
                atomic_json(root / 'sti-config.json', old_config)
            else:
                (root / 'sti-config.json').unlink(missing_ok=True)
            if marker:
                atomic_json(root / 'installation.json', marker)
            else:
                (root / 'installation.json').unlink(missing_ok=True)
            if had_agent and launch:
                launch_agent(root)
            raise
        if launch:
            try:
                confirm_agent_start(root, version)
            except Exception:
                logger.exception('Arquivos instalados, mas a inicialização do agente não foi confirmada.')
                raise
        logger.info('Instalação concluída. inicialização solicitada=%s', launch)
    return root


def remove_installation(root, unregister=True):
    root = Path(root).resolve()
    installation_marker(root)
    with installation_lock(root):
        stop_installed_agent(root)
        if unregister:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
                try:
                    command = winreg.QueryValueEx(key, PRODUCT)[0]
                    if str(root / AGENT_FILENAME).casefold() in command.casefold():
                        winreg.DeleteValue(key, PRODUCT)
                except FileNotFoundError:
                    pass
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Uninstall\AgenteSTI')
            except FileNotFoundError:
                pass
        for name in (AGENT_FILENAME, 'STI_Agente_Setup.exe', 'previous-agent.exe', 'incoming-agent.exe', 'installation.json'):
            (root / name).unlink(missing_ok=True)

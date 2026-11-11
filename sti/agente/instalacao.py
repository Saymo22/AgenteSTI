"""Instalação Windows por usuário e operações usadas pelo atualizador."""
import contextlib
import ctypes
import hashlib
import json
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
CONFIG_KEYS = {'STI_SERVER_IP', 'STI_SERVER_PORT', 'STI_AGENT_TOKEN', 'STI_USE_HTTPS',
               'STI_ALLOW_POWER_COMMANDS', 'STI_IDENTITY_FILE', 'AGENT_INTERVAL', 'RETRY_INTERVAL'}


def default_install_root():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'STI' / 'Agent'


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
            same_installation = path == executable
            legacy = include_legacy and path and path.name.casefold() in legacy_names and process.username() == owner
            if process.pid != os.getpid() and (same_installation or legacy):
                matching.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    for process in reversed(matching):
        try:
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
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    old_config = read_json(root / 'sti-config.json', {})
    merged_config = validate_config({**old_config, **config})
    marker = read_json(root / 'installation.json', {})
    if marker.get('version') and version_tuple(marker['version']) > version_tuple(version):
        raise ValueError('A versão instalada é mais recente. Utilize o instalador atual.')
    with installation_lock(root):
        executable = root / AGENT_FILENAME
        backup = root / 'previous-agent.exe'
        had_agent = executable.exists()
        incoming = root / 'incoming-agent.exe'
        shutil.copyfile(payload, incoming)
        stop_installed_agent(root, include_legacy=True)
        moved_backup = False
        installed_new = False
        try:
            if had_agent:
                replace_retry(executable, backup)
                moved_backup = True
            replace_retry(incoming, executable)
            installed_new = True
            atomic_json(root / 'sti-config.json', merged_config)
            atomic_json(root / 'installation.json', {'product': PRODUCT, 'root': str(root),
                        'install_id': marker.get('install_id') or str(uuid.uuid4()), 'version': version,
                        'startup': startup, 'registered': register})
            if setup_source:
                destination = root / 'STI_Agente_Setup.exe'
                if Path(setup_source).resolve() != destination:
                    shutil.copyfile(setup_source, destination)
            if register:
                register_windows(root, version, startup)
        except Exception:
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
            launch_agent(root)
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

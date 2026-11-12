"""Integração explícita do agente com o Windows Installer, sem trocar executáveis."""
import ctypes
import logging
import os
import subprocess
import time
from pathlib import Path

from sti.comum.msi import REGISTRY_KEY, UPGRADE_CODE
from sti.comum.releases import atomic_json, read_json


def installation(root):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        values = {name: winreg.QueryValueEx(key, name)[0] for name in ('InstallDir', 'ProductCode', 'Startup')}
    if Path(values['InstallDir']).resolve() != Path(root).resolve():
        raise ValueError('O executável não pertence à instalação MSI registrada.')
    api = ctypes.WinDLL('msi')
    api.MsiQueryProductStateW.argtypes = [ctypes.c_wchar_p]
    if api.MsiQueryProductStateW(values['ProductCode']) != 5:
        raise ValueError('O produto MSI não está instalado para este usuário.')
    return values


def package_properties(path):
    """Inspeção somente leitura; não carrega código do pacote."""
    api = ctypes.WinDLL('msi')
    handle = ctypes.c_uint
    api.MsiOpenDatabaseW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(handle)]
    api.MsiDatabaseOpenViewW.argtypes = [handle, ctypes.c_wchar_p, ctypes.POINTER(handle)]
    api.MsiViewExecute.argtypes = [handle, handle]
    api.MsiViewFetch.argtypes = [handle, ctypes.POINTER(handle)]
    api.MsiRecordGetStringW.argtypes = [handle, ctypes.c_uint, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint)]
    api.MsiCloseHandle.argtypes = [handle]
    database, view = handle(), handle()
    if api.MsiOpenDatabaseW(str(Path(path).resolve()), None, ctypes.byref(database)):
        raise ValueError('Pacote MSI inválido.')
    result = {}
    try:
        if api.MsiDatabaseOpenViewW(database, 'SELECT `Property`, `Value` FROM `Property`', ctypes.byref(view)) or api.MsiViewExecute(view, 0):
            raise ValueError('Não foi possível inspecionar o MSI.')
        while True:
            record = handle()
            code = api.MsiViewFetch(view, ctypes.byref(record))
            if code == 259:
                break
            if code:
                raise ValueError('Tabela de propriedades MSI inválida.')
            try:
                fields = []
                for index in (1, 2):
                    size = ctypes.c_uint(32768)
                    buffer = ctypes.create_unicode_buffer(size.value)
                    if api.MsiRecordGetStringW(record, index, buffer, ctypes.byref(size)):
                        raise ValueError('Propriedade MSI inválida.')
                    fields.append(buffer.value)
                result[fields[0]] = fields[1]
            finally:
                api.MsiCloseHandle(record)
    finally:
        if view.value:
            api.MsiCloseHandle(view)
        api.MsiCloseHandle(database)
    return result


def verify_package(path, version):
    from sti.comum.msi import product_code
    props = package_properties(path)
    if (props.get('UpgradeCode') != UPGRADE_CODE or props.get('ProductCode') != product_code(version)
            or props.get('ProductVersion') != version or props.get('ALLUSERS')):
        raise ValueError('O MSI não corresponde ao produto, versão ou modo de instalação esperado.')


def configure(root, config_source='', original_database=''):
    from sti.agente.instalacao import validate_config, configure_install_logging
    configure_install_logging()
    root = Path(root).resolve()
    target = root / 'sti-config.json'
    source = target if target.is_file() else Path(config_source or str(Path(original_database).parent / 'agent-config.json'))
    clean = validate_config(read_json(source))
    if not target.is_file():
        atomic_json(target, clean)
    # Only remove the obsolete custom uninstall entry if it belongs to this directory.
    import winreg
    legacy = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\AgenteSTI'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, legacy) as key:
            same_root = Path(winreg.QueryValueEx(key, 'InstallLocation')[0]).resolve() == root
        if same_root:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, legacy)
    except FileNotFoundError:
        pass


def launch(previous_pid='', reboot_pending=''):
    from sti.comum.empacotamento import executable_path
    root = executable_path().parent
    if previous_pid:
        import psutil
        try:
            process = psutil.Process(int(previous_pid))
            if Path(process.exe()).resolve() == executable_path().resolve():
                process.wait(timeout=45)
        except psutil.NoSuchProcess:
            pass
    if reboot_pending:
        from sti.agente.atualizacao import save_status, state_path
        saved = read_json(state_path(root), {})
        save_status(root, 'deferred', saved.get('target_version', ''), saved.get('rollout_id', ''),
                    'O Windows Installer solicita reiniciar o Windows para concluir a atualização.')
    env = os.environ.copy()
    # A process started after installation must own its PyInstaller extraction directory.
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    env['STI_CONFIG_FILE'] = str(root / 'sti-config.json')
    subprocess.Popen([str(root / 'STI_Agente.exe')], cwd=root, env=env,
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def entry(arguments):
    try:
        if arguments[0] == '--msi-configure' and len(arguments) == 4:
            configure(*arguments[1:])
        elif arguments[0] == '--msi-launch' and len(arguments) == 3:
            launch(*arguments[1:])
        else:
            raise ValueError('Argumentos MSI inválidos.')
        return 0
    except Exception:
        logging.getLogger('STI_INSTALL').exception('A operação do Windows Installer falhou.')
        return 1

"""Migração de dados; nunca executa binários da instalação por usuário como SYSTEM."""
import logging
import os
import re
import sqlite3
import tempfile
import uuid
from contextlib import closing
from pathlib import Path

from sti.comum.releases import atomic_json, read_json
from sti.comum.servico import data_dir, SERVICE_NAME

logger = logging.getLogger('STI_INSTALL')


def reject_reparse(path):
    for part in (Path(path), *Path(path).parents):
        if part.is_symlink() or (part.exists() and part.stat().st_file_attributes & 0x400):
            raise ValueError('Caminho com redirecionamento não é permitido para o serviço.')


def protect_directory(root):
    import win32security
    import ntsecuritycon
    root = Path(root)
    reject_reparse(root)
    system = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
    admins = win32security.CreateWellKnownSid(win32security.WinBuiltinAdministratorsSid, None)
    trusted = {str(system), str(admins)}
    if root.exists():
        # ProgramData permite criar diretórios. Nunca promover dados pré-criados por um usuário
        # a configuração/código de comandos de um serviço SYSTEM só por mudar suas permissões.
        for part in (root, *root.rglob('*')):
            reject_reparse(part)
            security = win32security.GetNamedSecurityInfo(str(part), win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION)
            acl = security.GetSecurityDescriptorDacl()
            if str(security.GetSecurityDescriptorOwner()) not in trusted or acl is None:
                raise ValueError('Pasta de dados preexistente sem proprietário confiável. Faça a verificação administrativa antes de instalar.')
            for index in range(acl.GetAceCount()):
                ace = acl.GetAce(index)
                if ace[0][0] != win32security.ACCESS_ALLOWED_ACE_TYPE or str(ace[-1]) not in trusted:
                    raise ValueError('A pasta de dados preexistente possui permissões incompatíveis com o serviço.')
    root.mkdir(parents=True, exist_ok=True)
    acl = win32security.ACL()
    for sid in (system, admins):
        acl.AddAccessAllowedAceEx(win32security.ACL_REVISION_DS, 3, ntsecuritycon.FILE_ALL_ACCESS, sid)
    win32security.SetNamedSecurityInfo(str(root), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION |
        win32security.OWNER_SECURITY_INFORMATION, system, None, acl, None)
    # Não confiar em filhos que tenham sido criados antes da instalação elevada.
    for child in root.rglob('*'):
        reject_reparse(child)
        win32security.SetNamedSecurityInfo(str(child), win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION |
            win32security.OWNER_SECURITY_INFORMATION, system, None, acl, None)


def read_config(path):
    from sti.agente.instalacao import validate_config
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('Informe um agent-config.json válido para instalar o serviço.')
    return validate_config(read_json(path))


def read_identity(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Identidade anterior ausente ou inválida; confirme a pasta de migração.')
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)) as conn:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(identity)')}
        row = conn.execute('SELECT agent_id,hardware_key,' + ('key_kind' if 'key_kind' in columns else "''") + ' FROM identity WHERE id=1').fetchone()
    if not row or not all(isinstance(value, str) for value in row):
        raise ValueError('Identidade anterior corrompida.')
    agent_id = str(uuid.UUID(row[0]))
    if len(row[1]) > 128 or len(row[2]) > 32:
        raise ValueError('Identidade anterior inválida.')
    return agent_id, row[1], row[2]


def migrate_journal(source, target, agent_id):
    if not source.is_file() or target.exists():
        return
    if source.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Histórico de comandos anterior excede o limite de migração.')
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)) as conn:
        identity = conn.execute('SELECT agent_id FROM journal_identity WHERE id=1').fetchone()
        if not identity or identity[0] != agent_id:
            return
        rows = conn.execute('SELECT id,command,message,stage,status,result,updated_at FROM jobs LIMIT 10001').fetchall()
    if len(rows) > 10000:
        raise ValueError('Histórico de comandos anterior excede o limite de migração.')
    clean = []
    for identifier, command, message, stage, status, result, updated_at in rows:
        uuid.UUID(identifier)
        if command not in ('msg', 'shutdown', 'restart') or stage not in ('received','running','result','acknowledged'):
            raise ValueError('Histórico de comandos inválido.')
        if not all(isinstance(value, str) for value in (message, status, result)):
            raise ValueError('Histórico de comandos inválido.')
        if stage in ('received','running'):
            stage, status, result = 'result', 'failed', 'Migração para serviço; execução anterior incerta. Não reexecutado.'
        clean.append((identifier, command, message[:500], stage, status[:30], result[:500], float(updated_at)))
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix='commands-migration-', suffix='.db', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with closing(sqlite3.connect(temporary)) as conn, conn:
            conn.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY,command TEXT NOT NULL,message TEXT NOT NULL,stage TEXT NOT NULL,status TEXT NOT NULL DEFAULT "",result TEXT NOT NULL DEFAULT "",updated_at REAL NOT NULL)')
            conn.execute('CREATE TABLE journal_identity (id INTEGER PRIMARY KEY CHECK(id=1),agent_id TEXT NOT NULL)')
            conn.execute('INSERT INTO journal_identity VALUES (1,?)', (agent_id,))
            conn.executemany('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)', clean)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def configure_service(install_root, config_source='', original_database='', legacy_root='', user_sid=''):
    from sti.agente.instalacao import configure_install_logging
    expected = Path(os.environ.get('ProgramW6432', os.environ.get('ProgramFiles', r'C:\Program Files'))) / 'STI' / 'AgentService'
    if Path(install_root).resolve() != expected.resolve():
        raise ValueError('Instale o serviço na pasta protegida padrão em Program Files.')
    reject_reparse(expected)
    root = data_dir()
    protect_directory(root)
    configure_install_logging(root)
    target = root / 'sti-config.json'
    legacy = Path(legacy_root).resolve() if legacy_root else None
    if target.is_file():
        source = target
    elif config_source:
        # Um caminho explícito inválido deve ser corrigido, não ignorado.
        source = Path(config_source)
    else:
        previous_config = legacy / 'sti-config.json' if legacy else None
        source = previous_config if previous_config and previous_config.is_file() else Path(original_database).parent / 'agent-config.json'
    config = read_config(source)
    identity = root / 'identity.db'
    if not identity.exists():
        configured = config.get('STI_IDENTITY_FILE')
        shared = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'STI' / 'identity.db'
        configured_path = Path(configured) if configured else None
        if configured_path and not configured_path.is_absolute():
            configured_path = source.parent / configured_path
        candidates = [configured_path] if configured_path else [shared, legacy.parent/'identity.db'] if legacy else [shared]
        previous = next((path for path in candidates if path.is_file()), None)
        if previous:
            if str(previous).startswith('\\\\'):
                raise ValueError('A identidade de migração deve estar em um arquivo local.')
            record = read_identity(previous)
            if legacy:
                migrate_journal(legacy.parent/'commands.db', root/'commands.db', record[0])
            with closing(sqlite3.connect(identity)) as conn, conn:
                conn.execute('CREATE TABLE identity (id INTEGER PRIMARY KEY CHECK(id=1), agent_id TEXT NOT NULL,hardware_key TEXT NOT NULL,key_kind TEXT NOT NULL)')
                conn.execute('INSERT INTO identity VALUES (1,?,?,?)', record)
        elif legacy:
            raise ValueError('Não foi encontrada a identidade antiga. Confirme a pasta e STI_IDENTITY_FILE; o cadastro não será recriado silenciosamente.')
    else:
        read_identity(identity)
    config['STI_IDENTITY_FILE'] = str(identity)
    atomic_json(target, config)
    if legacy:
        atomic_json(root/'migration.json', {'legacy_root':str(legacy), 'user_sid':user_sid, 'pending':True})
    logger.info('Configuração do serviço preparada. Identidade e credenciais não são registradas no log.')


def configure_recovery():
    import win32service
    from sti.agente.instalacao import configure_install_logging
    configure_install_logging(data_dir())
    manager = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
    try:
        service = win32service.OpenService(manager, SERVICE_NAME, win32service.SERVICE_CHANGE_CONFIG)
        try:
            win32service.ChangeServiceConfig2(service, win32service.SERVICE_CONFIG_FAILURE_ACTIONS,
                {'ResetPeriod':86400, 'RebootMsg':'', 'Command':'',
                 'Actions':[(win32service.SC_ACTION_RESTART, 60000)] * 3})
            win32service.ChangeServiceConfig2(service, win32service.SERVICE_CONFIG_FAILURE_ACTIONS_FLAG, True)
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(manager)


def commit_migration(legacy_root, user_sid):
    """Só desativa o startup do usuário instalador, se o caminho registrado conferir."""
    import winreg
    import win32service
    import psutil
    from sti.comum.msi import REGISTRY_KEY
    from sti.agente.instalacao import configure_install_logging
    configure_install_logging(data_dir())
    if not legacy_root:
        return
    if win32serviceutil_status() != win32service.SERVICE_RUNNING:
        logger.warning('Serviço ainda não iniciado; startup antigo preservado.')
        return
    legacy = Path(legacy_root).resolve()
    candidates = [user_sid]
    for index in range(winreg.QueryInfoKey(winreg.HKEY_USERS)[0]):
        candidates.append(winreg.EnumKey(winreg.HKEY_USERS, index))
    matched = False
    for sid in dict.fromkeys(candidates):
        if not re.fullmatch(r'S-1-5-(?:\d+-)*\d+', sid):
            continue
        prefix = sid+'\\'
        try:
            with winreg.OpenKey(winreg.HKEY_USERS, prefix+REGISTRY_KEY) as key:
                if Path(winreg.QueryValueEx(key, 'InstallDir')[0]).resolve() != legacy:
                    continue
            matched = True
            with winreg.OpenKey(winreg.HKEY_USERS, prefix+r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
                value = winreg.QueryValueEx(key, 'AgenteSTI')[0]
                if str(value).strip().strip('"').casefold() == str(legacy/'STI_Agente.exe').casefold():
                    winreg.DeleteValue(key, 'AgenteSTI')
        except FileNotFoundError:
            continue
    if not matched:
        logger.info('Migração aguardando o perfil anterior ficar disponível; nenhuma entrada de outro usuário foi alterada.')
        return
    for process in psutil.process_iter(['pid','exe']):
        try:
            if process.pid != os.getpid() and process.info['exe'] and Path(process.info['exe']).resolve() == legacy/'STI_Agente.exe':
                process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            logger.warning('Não foi possível encerrar uma instância anterior; confira a sessão do usuário.')
    logger.info('Migração concluída; inicialização antiga do usuário desativada. Arquivos antigos preservados.')
    atomic_json(data_dir()/'migration.json', {'legacy_root':str(legacy), 'user_sid':user_sid, 'pending':False})


def retry_migration():
    saved = read_json(data_dir()/'migration.json', {})
    if saved.get('pending'):
        try:
            commit_migration(saved['legacy_root'], saved.get('user_sid', ''))
        except (OSError, ValueError):
            logger.warning('A limpeza da instalação anterior aguarda o perfil do usuário.', exc_info=True)


def win32serviceutil_status():
    import win32serviceutil
    return win32serviceutil.QueryServiceStatus(SERVICE_NAME)[1]

"""Atualização assinada pelo Windows Installer, sem substituir arquivos manualmente."""
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path

import requests
from sti.agente.msi import installation, verify_package
from sti.comum.releases import (AGENT_FILENAME, MAX_PACKAGE, atomic_json, read_json,
                               verify_manifest, verify_file, version_tuple)
from sti.comum.versao import AGENT_VERSION
from sti.comum.empacotamento import is_bundled, executable_path

logger = logging.getLogger('STI_AGENT')
pending_offer = None
next_attempt = 0
health_sent = False


def installed_root():
    if not is_bundled():
        return None
    root = executable_path().parent
    if executable_path().name.casefold() != AGENT_FILENAME.casefold():
        return None
    try:
        installation(root)
    except (OSError, ValueError, KeyError, ImportError):
        return None
    return root


def state_path(root):
    return Path(root).parent / 'update-state.json'


def update_report():
    root = installed_root()
    if not root:
        return {'update_supported': False, 'update_protocol': 2}
    try:
        saved = read_json(state_path(root), {})
        report = {key: saved.get(key, '') for key in ('status', 'target_version', 'result')}
        report['status'] = report['status'] or 'idle'
    except (ValueError, OSError, AttributeError):
        report = {'status': 'failed', 'target_version': '', 'result': 'Não foi possível ler o estado local da atualização.'}
    return {'update_supported': True, 'update_protocol': 2, 'update_status': report}


def remember_offer(offer):
    global pending_offer
    pending_offer = offer if isinstance(offer, dict) else None


def acknowledge_health():
    global health_sent
    root = installed_root()
    if not root or health_sent:
        return
    saved = read_json(state_path(root), {})
    if saved.get('status') in ('installing', 'deferred'):
        if saved.get('target_version') == AGENT_VERSION:
            save_status(root, 'updated', AGENT_VERSION, saved.get('rollout_id', ''),
                        'Versão MSI confirmada pela comunicação com o servidor.')
        elif saved.get('status') == 'installing':
            save_status(root, 'failed', saved.get('target_version', ''), saved.get('rollout_id', ''),
                        'O MSI não concluiu a atualização. Consulte o log do Windows Installer e o Endpoint.')
    health_sent = True


def save_status(root, status, version, rollout, result='', retryable=False):
    atomic_json(state_path(root), {'status': status, 'target_version': version,
                'rollout_id': rollout, 'result': str(result)[:500], 'retryable': retryable})


def download_package(session, url, headers, destination, expected_size):
    with session.get(url, headers=headers, stream=True, timeout=(5, 30), allow_redirects=False) as response:
        if response.status_code != 200:
            response.raise_for_status()
            raise ValueError(f'O servidor recusou o pacote de atualização ({response.status_code}).')
        received = 0
        with Path(destination).open('wb') as output:
            for chunk in response.iter_content(1024 * 1024):
                received += len(chunk)
                if received > expected_size or received > MAX_PACKAGE:
                    raise ValueError('O pacote ultrapassou o tamanho assinado.')
                output.write(chunk)
        if received != expected_size:
            raise requests.exceptions.ChunkedEncodingError('Download incompleto.')


def report_progress(session, server_url, token, agent_id, root):
    try:
        status = read_json(state_path(root), {})
        session.post(server_url.rstrip('/') + '/api/agent/update-status',
                     headers={'X-Agent-Token': token}, timeout=(4, 10), allow_redirects=False,
                     json={'agent_id': agent_id, 'agent_version': AGENT_VERSION, 'update_supported': True,
                           'update_protocol': 2, 'update_status': status}).raise_for_status()
    except (OSError, ValueError, requests.RequestException):
        logger.warning('Não foi possível informar o andamento da atualização ao servidor.')


def begin_update(session, server_url, token, agent_id, config_file):
    global next_attempt
    root = installed_root()
    offer = pending_offer
    if not root or not offer or time.monotonic() < next_attempt:
        return False
    next_attempt = time.monotonic() + 300
    version = ''
    rollout = str(offer.get('rollout_id', ''))
    try:
        uuid.UUID(rollout)
        manifest = verify_manifest(offer['release'])
        if manifest['format'] != 2:
            raise ValueError('Este agente requer uma release MSI.')
        version = manifest['version']
        if version_tuple(version) <= version_tuple(AGENT_VERSION):
            return False
        previous = read_json(state_path(root), {})
        failed_release = previous.get('status') in ('rolled_back', 'deferred') or (previous.get('status') == 'failed' and not previous.get('retryable'))
        if failed_release and previous.get('target_version') == version and previous.get('rollout_id') == rollout:
            return False
        staging = root.parent / 'updates' / str(uuid.uuid4())
        staging.mkdir(parents=True)
        save_status(root, 'downloading', version, rollout)
        report_progress(session, server_url, token, agent_id, root)
        package = staging / 'installer.msi'
        # O token só é enviado ao servidor configurado. Caminhos fornecidos na resposta não são utilizados.
        url = server_url.rstrip('/') + f'/api/agent/releases/{version}/package'
        download_package(session, url, {'X-Agent-Token': token, 'X-Agent-ID': agent_id}, package, manifest['package']['size'])
        verify_file(package, manifest['installer'])
        verify_package(package, version)
        startup = installation(root)['Startup']
        save_status(root, 'installing', version, rollout)
        report_progress(session, server_url, token, agent_id, root)
        installer = Path(os.environ['SystemRoot']) / 'System32' / 'msiexec.exe'
        logfile = staging / 'windows-installer.log'
        env = os.environ.copy()
        env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        subprocess.Popen([str(installer), '/i', str(package), '/qn', '/norestart', '/l*v', str(logfile),
                          'STI_PREVIOUS_PID=' + str(os.getpid()), 'STI_STARTUP=' + str(startup)], cwd=staging, env=env,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        logger.info('Atualizador iniciado para a versão %s.', version)
        return True
    except (OSError, ValueError, KeyError, requests.RequestException) as error:
        logger.exception('Atualização não iniciada.')
        save_status(root, 'failed', version, rollout, error, retryable=isinstance(error, (OSError, requests.RequestException)))
        report_progress(session, server_url, token, agent_id, root)
        return False

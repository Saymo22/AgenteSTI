"""Download verificado, troca do executável e recuperação da versão anterior."""
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psutil
import requests
from sti.agente.instalacao import installation_marker, installation_lock, launch_agent, replace_retry, register_windows
from sti.comum.releases import (AGENT_FILENAME, MAX_PACKAGE, atomic_json, read_json,
                               verify_manifest, unpack_agent, version_tuple, file_hash)
from sti.comum.versao import AGENT_VERSION

logger = logging.getLogger('STI_AGENT')
pending_offer = None
next_attempt = 0
health_sent = False


def installed_root():
    if not getattr(sys, 'frozen', False):
        return None
    root = Path(sys.executable).resolve().parent
    if Path(sys.executable).name.casefold() != AGENT_FILENAME.casefold():
        return None
    try:
        installation_marker(root)
    except (OSError, ValueError, KeyError):
        return None
    return root


def state_path(root):
    return Path(root).parent / 'update-state.json'


def update_report():
    root = installed_root()
    if not root:
        return {'update_supported': False, 'update_protocol': 1}
    try:
        saved = read_json(state_path(root), {})
        report = {key: saved.get(key, '') for key in ('status', 'target_version', 'result')}
        report['status'] = report['status'] or 'idle'
    except (ValueError, OSError, AttributeError):
        report = {'status': 'failed', 'target_version': '', 'result': 'Não foi possível ler o estado local da atualização.'}
    return {'update_supported': True, 'update_protocol': 1, 'update_status': report}


def remember_offer(offer):
    global pending_offer
    pending_offer = offer if isinstance(offer, dict) else None


def acknowledge_health():
    global health_sent
    destination = os.environ.get('STI_UPDATE_HEALTH_FILE')
    nonce = os.environ.get('STI_UPDATE_HEALTH_NONCE')
    if destination and nonce:
        atomic_json(destination, {'nonce': nonce, 'version': AGENT_VERSION})
        os.environ.pop('STI_UPDATE_HEALTH_FILE', None)
        os.environ.pop('STI_UPDATE_HEALTH_NONCE', None)
        health_sent = True
        return
    root = installed_root()
    if not root or health_sent:
        return
    saved = read_json(state_path(root), {})
    if saved.get('status') == 'installing':
        if saved.get('target_version') == AGENT_VERSION:
            marker = installation_marker(root)
            marker['version'] = AGENT_VERSION
            atomic_json(root / 'installation.json', marker)
            if marker.get('registered', True):
                register_windows(root, AGENT_VERSION, marker.get('startup', True))
            save_status(root, 'updated', AGENT_VERSION, saved.get('rollout_id', ''), 'Atualização confirmada após reinicialização.')
        else:
            save_status(root, 'failed', saved.get('target_version', ''), saved.get('rollout_id', ''), 'Atualização interrompida; versão anterior em execução. Libere a distribuição novamente para tentar outra vez.')
    health_sent = True


def cleanup_staging(root):
    base = Path(root).parent / 'updates'
    if not base.is_dir():
        return
    for folder in base.iterdir():
        try:
            uuid.UUID(folder.name)
            if not folder.is_dir() or folder.is_symlink() or folder.resolve().parent != base.resolve():
                continue
            # No Windows, uma cópia do atualizador ainda em execução permanece bloqueada.
            (folder / 'STI_Update.exe').unlink(missing_ok=True)
            for name in ('agent.zip', 'plan.json', 'health.json', 'incoming.exe', 'verified-agent.exe', 'plan.json.tmp', 'health.json.tmp'):
                (folder / name).unlink(missing_ok=True)
            folder.rmdir()
        except (ValueError, OSError):
            continue


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
                           'update_protocol': 1, 'update_status': status}).raise_for_status()
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
        version = manifest['version']
        if version_tuple(version) <= version_tuple(AGENT_VERSION):
            return False
        previous = read_json(state_path(root), {})
        failed_release = previous.get('status') == 'rolled_back' or (previous.get('status') == 'failed' and not previous.get('retryable'))
        if failed_release and previous.get('target_version') == version and previous.get('rollout_id') == rollout:
            return False
        cleanup_staging(root)
        staging = root.parent / 'updates' / str(uuid.uuid4())
        staging.mkdir(parents=True)
        save_status(root, 'downloading', version, rollout)
        report_progress(session, server_url, token, agent_id, root)
        package = staging / 'agent.zip'
        # O token só é enviado ao servidor configurado. Caminhos fornecidos na resposta não são utilizados.
        url = server_url.rstrip('/') + f'/api/agent/releases/{version}/package'
        download_package(session, url, {'X-Agent-Token': token, 'X-Agent-ID': agent_id}, package, manifest['package']['size'])
        unpack_agent(package, staging / 'verified-agent.exe', manifest)
        (staging / 'verified-agent.exe').unlink()
        helper = staging / 'STI_Update.exe'
        shutil.copyfile(sys.executable, helper)
        plan = {'root': str(root), 'package': str(package), 'release': offer['release'],
                'rollout_id': rollout, 'parent_pid': os.getpid(), 'config_file': str(config_file),
                'previous_agent_hash': file_hash(sys.executable),
                'nonce': str(uuid.uuid4()), 'health_file': str(staging / 'health.json')}
        atomic_json(staging / 'plan.json', plan)
        save_status(root, 'installing', version, rollout)
        report_progress(session, server_url, token, agent_id, root)
        subprocess.Popen([str(helper), '--apply-update', str(staging / 'plan.json')], cwd=staging,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        logger.info('Atualizador iniciado para a versão %s.', version)
        return True
    except (OSError, ValueError, KeyError, requests.RequestException) as error:
        logger.exception('Atualização não iniciada.')
        save_status(root, 'failed', version, rollout, error, retryable=isinstance(error, (OSError, requests.RequestException)))
        report_progress(session, server_url, token, agent_id, root)
        return False


def stop_launched_process(process):
    try:
        parent = psutil.Process(process.pid)
        owned = parent.children(recursive=True) + [parent]
        for child in owned:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(owned, timeout=10)
        if alive:
            raise RuntimeError('A versão nova não encerrou para permitir a recuperação.')
    except psutil.NoSuchProcess:
        pass


def run_update_helper(plan_file):
    try:
        return apply_plan(plan_file)
    except Exception as error:
        logger.exception('O atualizador não conseguiu concluir a preparação ou recuperação.')
        # Uma falha de validação pode ocorrer depois que o agente original encerrou.
        # Só reinicie se o arquivo instalado ainda for exatamente o original.
        try:
            path = Path(plan_file).resolve()
            plan = read_json(path)
            root = Path(plan['root']).resolve()
            installation_marker(root)
            if path.parent.parent != root.parent / 'updates':
                raise ValueError('Plano fora da pasta de atualizações.')
            with installation_lock(root):
                if file_hash(root / AGENT_FILENAME) != plan['previous_agent_hash']:
                    raise ValueError('Executável original indisponível para reiniciar.')
                try:
                    psutil.Process(int(plan['parent_pid'])).wait(timeout=45)
                except psutil.NoSuchProcess:
                    pass
                version = plan['release']['manifest']['version']
                version_tuple(version)
                save_status(root, 'failed', version, plan['rollout_id'], error)
                launch_agent(root, config_file=plan.get('config_file'))
        except Exception:
            logger.exception('Não foi possível reiniciar automaticamente o agente original.')
        return False


def apply_plan(plan_file, health_timeout=90):
    plan_file = Path(plan_file).resolve()
    plan = read_json(plan_file)
    root = Path(plan['root']).resolve()
    marker = installation_marker(root)
    original_version = marker['version']
    staging = plan_file.parent
    if not staging.is_relative_to(root.parent / 'updates'):
        raise ValueError('Diretório de atualização não reconhecido.')
    package = Path(plan['package']).resolve()
    health_file = Path(plan['health_file']).resolve()
    if package.parent != staging or health_file.parent != staging:
        raise ValueError('Arquivo de atualização fora do diretório esperado.')
    manifest = verify_manifest(plan['release'])
    version = manifest['version']
    if version_tuple(version) <= version_tuple(marker['version']):
        raise ValueError('A instalação já possui essa versão ou uma mais recente.')
    incoming = staging / 'incoming.exe'
    unpack_agent(package, incoming, manifest)
    executable = root / AGENT_FILENAME
    backup = root / 'previous-agent.exe'
    child = None
    replaced = False
    with installation_lock(root):
        try:
            current_marker = installation_marker(root)
            if version_tuple(version) <= version_tuple(current_marker['version']):
                return False
            marker = current_marker
            original_version = marker['version']
            try:
                psutil.Process(int(plan['parent_pid'])).wait(timeout=45)
            except psutil.NoSuchProcess:
                pass
            replace_retry(executable, backup)
            replaced = True
            replace_retry(incoming, executable)
            child = launch_agent(root, {'STI_UPDATE_HEALTH_FILE': str(health_file),
                                'STI_UPDATE_HEALTH_NONCE': plan['nonce']}, plan.get('config_file'))
            deadline = time.monotonic() + health_timeout
            while time.monotonic() < deadline:
                health = read_json(health_file, {})
                if health.get('nonce') == plan['nonce'] and health.get('version') == version:
                    marker['version'] = version
                    atomic_json(root / 'installation.json', marker)
                    if marker.get('registered', True):
                        register_windows(root, version, marker.get('startup', True))
                    save_status(root, 'updated', version, plan['rollout_id'], 'Nova versão iniciou e comunicou com o servidor.')
                    return True
                if child.poll() is not None:
                    raise RuntimeError('A versão nova encerrou antes de confirmar a inicialização.')
                time.sleep(.5)
            raise RuntimeError('A versão nova não confirmou comunicação com o servidor dentro do prazo.')
        except Exception as error:
            if child:
                stop_launched_process(child)
            if replaced and backup.exists():
                replace_retry(backup, executable)
                # Versão anterior e configuração permanecem disponíveis para o próximo login.
                marker['version'] = original_version
                atomic_json(root / 'installation.json', marker)
                save_status(root, 'rolled_back', version, plan['rollout_id'], error)
                launch_agent(root, config_file=plan.get('config_file'))
            else:
                save_status(root, 'failed', version, plan['rollout_id'], error)
                launch_agent(root, config_file=plan.get('config_file'))
            return False

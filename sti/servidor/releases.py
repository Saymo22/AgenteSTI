"""Publicação autenticada de releases assinadas e política de distribuição."""
import json
import shutil
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from flask import jsonify, request, send_file

from sti.comum.releases import (MAX_BUNDLE, MAX_PACKAGE, MAX_BINARY, copy_limited,
                               verify_manifest, verify_file, unpack_agent, version_tuple)
from sti.comum.versao import AGENT_VERSION

publication_lock = threading.Lock()
UPDATE_STATUSES = {'idle', 'downloading', 'installing', 'updated', 'failed', 'rolled_back', 'deferred'}


def init_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS agent_releases (
        version TEXT PRIMARY KEY, envelope TEXT NOT NULL, created_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS agent_release_policy (
        id INTEGER PRIMARY KEY CHECK(id=1), policy TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS agent_update_state (
        device_id TEXT PRIMARY KEY, installed_version TEXT NOT NULL, supported INTEGER NOT NULL,
        status TEXT NOT NULL, target_version TEXT NOT NULL, result TEXT NOT NULL, updated_at TEXT NOT NULL)''')


def validate_update_status(data):
    supported = data.get('update_supported', False)
    if not isinstance(supported, bool):
        raise ValueError('update_supported deve ser booleano.')
    if data.get('update_protocol', 1) not in (1, 2):
        supported = False
    report = data.get('update_status', {})
    if not isinstance(report, dict):
        raise ValueError('Estado de atualização inválido.')
    status = report.get('status', 'idle')
    target = report.get('target_version', '')
    result = report.get('result', '')
    if not isinstance(status, str) or status not in UPDATE_STATUSES:
        raise ValueError('Estado de atualização desconhecido.')
    if target:
        version_tuple(target)
    if not isinstance(target, str) or not isinstance(result, str) or len(result) > 500:
        raise ValueError('Resultado de atualização inválido.')
    return supported, status, target, result


def record_heartbeat(conn, device_id, version, report):
    if not device_id:
        return
    conn.execute('''INSERT INTO agent_update_state VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(device_id) DO UPDATE SET installed_version=excluded.installed_version,
        supported=excluded.supported,status=excluded.status,target_version=excluded.target_version,
        result=excluded.result,updated_at=excluded.updated_at''',
        (device_id, version, *report, datetime.now().isoformat()))


def load_policy(conn):
    row = conn.execute('SELECT policy FROM agent_release_policy WHERE id=1').fetchone()
    return json.loads(row[0]) if row else None


def in_window(start, end, now=None):
    if not start or not end or start == end:
        return True
    clock = (now or datetime.now()).strftime('%H:%M')
    return start <= clock < end if start < end else clock >= start or clock < end


def update_offer(conn, device_id, version, supported, protocol=1):
    if not supported or not device_id:
        return None
    policy = load_policy(conn)
    if not policy or (policy['scope'] == 'selected' and device_id not in policy['device_ids']):
        return None
    if not in_window(policy['window_start'], policy['window_end']):
        return None
    try:
        if version_tuple(version) >= version_tuple(policy['version']):
            return None
    except ValueError:
        return None
    row = conn.execute('SELECT envelope FROM agent_releases WHERE version=?', (policy['version'],)).fetchone()
    if not row:
        return None
    envelope = json.loads(row[0])
    if envelope['manifest']['format'] != protocol:
        return None
    return {'release': envelope, 'rollout_id': policy['rollout_id'],
            'download_path': f"/api/agent/releases/{policy['version']}/package"}


def storage_path(db_file):
    return Path(db_file).resolve().parent / 'dados' / 'releases'


def import_bundle(bundle, root, conn):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='release-', dir=root) as temporary:
        staging = Path(temporary)
        with zipfile.ZipFile(bundle) as archive:
            if 'manifest.json' not in archive.namelist():
                raise ValueError('Manifesto da release não encontrado.')
            if archive.getinfo('manifest.json').file_size > 32768:
                raise ValueError('Manifesto da release excede o limite.')
            envelope = json.loads(archive.read('manifest.json'))
            manifest = verify_manifest(envelope)
            msi = manifest['format'] == 2
            files = [('installer.msi', MAX_BINARY)] if msi else [('agent.zip', MAX_PACKAGE), ('installer.exe', MAX_BINARY)]
            if sorted(archive.namelist()) != sorted(['manifest.json', *[name for name, _ in files]]):
                raise ValueError('Conteúdo da release incompatível com o manifesto.')
            for name, maximum in files:
                if archive.getinfo(name).file_size > maximum:
                    raise ValueError('Arquivo da release excede o limite.')
                with archive.open(name) as source:
                    copy_limited(source, staging / name, maximum)
        verify_file(staging / ('installer.msi' if msi else 'installer.exe'), manifest['installer'])
        if not msi:
            unpack_agent(staging / 'agent.zip', staging / 'verified-agent.exe', manifest)
            (staging / 'verified-agent.exe').unlink()
        version = manifest['version']
        existing = conn.execute('SELECT envelope FROM agent_releases WHERE version=?', (version,)).fetchone()
        if existing and json.loads(existing[0]) != envelope:
            raise ValueError('Essa versão já foi publicada com outro conteúdo. Gere uma versão nova.')
        destination = root / version
        if destination.exists():
            for name, _ in files:
                verify_file(destination / name, manifest['installer'] if name.startswith('installer.') else manifest['package'])
        else:
            destination.mkdir()
            try:
                for name, _ in files:
                    (staging / name).replace(destination / name)
            except Exception:
                # Somente arquivos conhecidos dentro do diretório desta versão recém-criada.
                for name, _ in files:
                    (destination / name).unlink(missing_ok=True)
                destination.rmdir()
                raise
        conn.execute('INSERT OR IGNORE INTO agent_releases VALUES (?,?,?)',
                     (version, json.dumps(envelope), datetime.now().isoformat()))
        return manifest


def register_routes(app, require_admin, db_connect, get_db_file, agent_authenticated, valid_ip):
    @app.get('/api/releases')
    @require_admin
    def list_releases():
        with db_connect() as conn:
            rows = conn.execute('SELECT version,envelope,created_at FROM agent_releases').fetchall()
            states = conn.execute('SELECT * FROM agent_update_state').fetchall()
            policy = load_policy(conn)
        rows.sort(key=lambda row: version_tuple(row[0]), reverse=True)
        return jsonify(ok=True, releases=[{'version': version, 'notes': json.loads(envelope)['manifest'].get('notes', ''),
            'created_at': created, 'installer_url': f'/api/releases/{version}/installer'} for version, envelope, created in rows],
            policy=policy, build_version=AGENT_VERSION, server_time=datetime.now().strftime('%H:%M'),
            devices=[dict(zip(('device_id', 'installed_version', 'supported', 'status', 'target_version', 'result', 'updated_at'), row)) for row in states])

    @app.post('/api/releases')
    @require_admin
    def upload_release():
        request.max_content_length = MAX_BUNDLE
        upload = request.files.get('release')
        if not upload:
            return jsonify(ok=False, error='Selecione o pacote de release assinado.'), 400
        root = storage_path(get_db_file())
        root.mkdir(parents=True, exist_ok=True)
        try:
            with publication_lock, tempfile.TemporaryFile(dir=root) as stream:
                shutil.copyfileobj(upload.stream, stream)
                stream.seek(0)
                with db_connect() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    manifest = import_bundle(stream, root, conn)
                    conn.execute('''INSERT INTO audit_events (timestamp,category,status,description)
                        VALUES (?, 'inventario', 'release_publicada', ?)''',
                        (datetime.now().isoformat(), 'Release ' + manifest['version'] + ' importada e assinatura verificada.'))
        except (ValueError, zipfile.BadZipFile, KeyError, OSError, RuntimeError) as error:
            return jsonify(ok=False, error=str(error)), 400
        return jsonify(ok=True, version=manifest['version']), 201

    @app.post('/api/releases/activate')
    @require_admin
    def activate_release():
        data = request.get_json(silent=True)
        try:
            if not isinstance(data, dict):
                raise ValueError('Configuração inválida.')
            version = data.get('version')
            version_tuple(version)
            scope = data.get('scope', 'all')
            ids = data.get('device_ids', [])
            if scope not in ('all', 'selected') or not isinstance(ids, list) or len(ids) > 4096:
                raise ValueError('Grupo de distribuição inválido.')
            ids = sorted({str(uuid.UUID(value)) for value in ids}) if scope == 'selected' else []
            if scope == 'selected' and not ids:
                raise ValueError('Selecione ao menos um equipamento para o grupo de teste.')
            start, end = data.get('window_start', ''), data.get('window_end', '')
            if not isinstance(start, str) or not isinstance(end, str):
                raise ValueError('Horário inválido.')
            if bool(start) != bool(end):
                raise ValueError('Informe início e fim da janela, ou deixe ambos vazios.')
            if start:
                start = datetime.strptime(start, '%H:%M').strftime('%H:%M')
                end = datetime.strptime(end, '%H:%M').strftime('%H:%M')
            policy = {'version': version, 'scope': scope, 'device_ids': ids,
                      'window_start': start, 'window_end': end, 'rollout_id': str(uuid.uuid4())}
        except (ValueError, TypeError, AttributeError) as error:
            return jsonify(ok=False, error=str(error)), 400
        with publication_lock, db_connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = load_policy(conn)
            if 'expected_rollout_id' in data and data['expected_rollout_id'] != (current or {}).get('rollout_id', ''):
                return jsonify(ok=False, error='A distribuição foi alterada em outra sessão. Recarregue a página antes de liberar novamente.'), 409
            if not conn.execute('SELECT 1 FROM agent_releases WHERE version=?', (version,)).fetchone():
                return jsonify(ok=False, error='Release não encontrada.'), 404
            registered = {row[0] for row in conn.execute('SELECT device_id FROM machine_inventory')}
            if set(ids) - registered:
                return jsonify(ok=False, error='Algum equipamento do grupo não está mais no inventário.'), 409
            conn.execute('INSERT OR REPLACE INTO agent_release_policy VALUES (1,?)', (json.dumps(policy),))
            conn.execute('''INSERT INTO audit_events (timestamp,category,status,description)
                VALUES (?, 'inventario', 'release_liberada', ?)''',
                (datetime.now().isoformat(), f'Release {version} liberada para {scope}.'))
        return jsonify(ok=True, policy=policy)

    @app.post('/api/releases/pause')
    @require_admin
    def pause_release():
        with db_connect() as conn:
            conn.execute('DELETE FROM agent_release_policy')
            conn.execute('''INSERT INTO audit_events (timestamp,category,status,description)
                VALUES (?, 'inventario', 'release_suspensa', 'Novas ofertas de atualização suspensas pelo administrador.')''',
                (datetime.now().isoformat(),))
        return jsonify(ok=True)

    @app.get('/api/releases/<version>/installer')
    @require_admin
    def installer_download(version):
        try:
            version_tuple(version)
        except ValueError:
            return jsonify(ok=False, error='Versão inválida.'), 400
        folder = storage_path(get_db_file()) / version
        msi = (folder / 'installer.msi').is_file()
        path = folder / ('installer.msi' if msi else 'installer.exe')
        if not path.is_file():
            return jsonify(ok=False, error='Instalador não encontrado.'), 404
        return send_file(path, as_attachment=True, download_name=f'STI_Agente_{version}.msi' if msi else f'STI_Agente_Setup_{version}.exe')

    @app.get('/api/agent/releases/<version>/package')
    def agent_package(version):
        if not agent_authenticated() or not valid_ip(request.remote_addr):
            return jsonify(ok=False, error='Agente não autorizado.'), 401
        try:
            version_tuple(version)
        except ValueError:
            return jsonify(ok=False, error='Versão inválida.'), 400
        with db_connect() as conn:
            binding = conn.execute('SELECT 1 FROM machine_inventory WHERE agent_id=? AND current_ip=?',
                                   (request.headers.get('X-Agent-ID', ''), request.remote_addr)).fetchone()
        if not binding:
            return jsonify(ok=False, error='Identidade do agente não corresponde ao endereço atual.'), 403
        folder = storage_path(get_db_file()) / version
        msi = (folder / 'installer.msi').is_file()
        path = folder / ('installer.msi' if msi else 'agent.zip')
        if not path.is_file():
            return jsonify(ok=False, error='Pacote não encontrado.'), 404
        return send_file(path, as_attachment=True, download_name=f'STI_Agente_{version}.msi' if msi else f'STI_Agente_{version}.zip')

    @app.post('/api/agent/update-status')
    def agent_update_status():
        if not agent_authenticated() or not valid_ip(request.remote_addr):
            return jsonify(ok=False, error='Agente não autorizado.'), 401
        data = request.get_json(silent=True)
        try:
            if not isinstance(data, dict):
                raise ValueError('Estado de atualização inválido.')
            version_tuple(data.get('agent_version'))
            report = validate_update_status(data)
        except (ValueError, TypeError) as error:
            return jsonify(ok=False, error=str(error)), 400
        with db_connect() as conn:
            row = conn.execute('SELECT device_id FROM machine_inventory WHERE agent_id=? AND current_ip=?',
                               (data.get('agent_id'), request.remote_addr)).fetchone()
            if not row:
                return jsonify(ok=False, error='Identidade do agente não corresponde ao endereço atual.'), 403
            record_heartbeat(conn, row[0], data['agent_version'], report)
        return jsonify(ok=True)

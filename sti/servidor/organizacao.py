"""Cadastro administrativo separado da telemetria enviada pelos agentes."""
from datetime import datetime
import uuid

from flask import jsonify, request

FIELDS = ("department", "room", "responsible", "display_name", "platform")
PLATFORMS = {'', 'Windows', 'Linux', 'Android', 'iOS', 'macOS', 'Impressora', 'Equipamento de rede', 'Outro'}


def migrate_identification(conn, table):
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
    for field in ('display_name', 'platform'):
        if field not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")


def empty_organization():
    return {**dict.fromkeys(FIELDS, ""), "updated_at": ""}


def init_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS device_organization (
        ip TEXT PRIMARY KEY,
        department TEXT NOT NULL DEFAULT '',
        room TEXT NOT NULL DEFAULT '',
        responsible TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL
    )""")
    migrate_identification(conn, 'device_organization')


def load_organizations(db_connect):
    with db_connect() as conn:
        rows = conn.execute("""SELECT ip, department, room, responsible, display_name, platform, updated_at
                               FROM device_organization""").fetchall()
        rows += conn.execute("SELECT device_id,department,room,responsible,display_name,platform,updated_at FROM machine_organization").fetchall()
    return {ip: dict(zip((*FIELDS, "updated_at"), values)) for ip, *values in rows}


def register_routes(app, require_admin, db_connect, devices, lock, valid_ip):
    @app.route("/api/devices/<reference>/organization", methods=["PATCH"])
    @require_admin
    def update_device_organization(reference):
        if not valid_ip(reference):
            try:
                reference = str(uuid.UUID(reference))
            except ValueError:
                return jsonify(ok=False,error='Identificador ou IP inválido'),400
        data = request.get_json(silent=True)
        allowed = {*FIELDS, "expected_updated_at"}
        if not isinstance(data, dict) or not data or set(data) - allowed or not set(data) & set(FIELDS):
            return jsonify(ok=False, error="Informe identificação, setor, sala ou responsável"), 400
        changes = {}
        for field in FIELDS:
            if field not in data:
                continue
            value = data[field]
            if (not isinstance(value, str) or len(value) > 120
                    or any(ord(character) < 32 for character in value)):
                return jsonify(ok=False, error="Os campos devem ser textos de até 120 caracteres, sem caracteres de controle"), 400
            changes[field] = value.strip()
        if 'platform' in changes and changes['platform'] not in PLATFORMS:
            return jsonify(ok=False, error='Sistema ou tipo de dispositivo inválido'), 400
        expected = data.get("expected_updated_at")
        if expected is not None and not isinstance(expected, str):
            return jsonify(ok=False, error="Versão do cadastro inválida"), 400
        with lock, db_connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            device = devices.get(reference)
            device_id = device.get('device_id') if device else reference
            registered = conn.execute("SELECT last_ip FROM machine_inventory WHERE device_id=?", (device_id,)).fetchone()
            if registered:
                ip = registered[0]
                table, key, value = 'machine_organization', 'device_id', device_id
            elif device and valid_ip(reference):
                ip, device_id = reference, None
                table, key, value = 'device_organization', 'ip', reference
            else:
                return jsonify(ok=False, error="Dispositivo não encontrado"), 404
            name = device['name'] if device else ''
            row = conn.execute(f"SELECT department,room,responsible,display_name,platform,updated_at FROM {table} WHERE {key}=?", (value,)).fetchone()
            current = dict(zip((*FIELDS, "updated_at"), row)) if row else empty_organization()
            if expected is not None and expected != current["updated_at"]:
                return jsonify(ok=False, error="Cadastro alterado em outra sessão. Reabra a máquina antes de salvar."), 409
            updated = {**current, **changes}
            if any(updated[field] != current[field] for field in FIELDS):
                updated["updated_at"] = datetime.now().isoformat()
                conn.execute(f"""INSERT INTO {table}
                    ({key}, department, room, responsible, display_name, platform, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT({key}) DO UPDATE SET department=excluded.department,
                        room=excluded.room, responsible=excluded.responsible, display_name=excluded.display_name,
                        platform=excluded.platform, updated_at=excluded.updated_at
                """, (value, *(updated[field] for field in FIELDS), updated["updated_at"]))
                description = (f"Cadastro atualizado — Setor: {updated['department'] or 'Não informado'}; "
                               f"Sala: {updated['room'] or 'Não informada'}; "
                               f"Responsável: {updated['responsible'] or 'Não informado'}; "
                               f"Nome cadastrado: {updated['display_name'] or 'Automático'}; "
                               f"Sistema cadastrado: {updated['platform'] or 'Automático'}")
                conn.execute("""INSERT INTO audit_events
                    (timestamp, category, ip, name, status, description, device_id)
                    VALUES (?, 'inventario', ?, ?, 'atualizado', ?, ?)""",
                    (updated["updated_at"], ip, name, description, device_id))
        return jsonify(ok=True, ip=ip, organization=updated)

"""Cadastro administrativo separado da telemetria enviada pelos agentes."""
from datetime import datetime

from flask import jsonify, request

FIELDS = ("department", "room", "responsible")


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


def load_organizations(db_connect):
    with db_connect() as conn:
        rows = conn.execute("""SELECT ip, department, room, responsible, updated_at
                               FROM device_organization""").fetchall()
    return {ip: dict(zip((*FIELDS, "updated_at"), values)) for ip, *values in rows}


def register_routes(app, require_admin, db_connect, devices, lock, valid_ip):
    @app.route("/api/devices/<ip>/organization", methods=["PATCH"])
    @require_admin
    def update_device_organization(ip):
        if not valid_ip(ip):
            return jsonify(ok=False, error="IP inválido"), 400
        data = request.get_json(silent=True)
        allowed = {*FIELDS, "expected_updated_at"}
        if not isinstance(data, dict) or not data or set(data) - allowed or not set(data) & set(FIELDS):
            return jsonify(ok=False, error="Informe setor, sala ou responsável"), 400
        changes = {}
        for field in FIELDS:
            if field not in data:
                continue
            value = data[field]
            if (not isinstance(value, str) or len(value) > 120
                    or any(ord(character) < 32 for character in value)):
                return jsonify(ok=False, error="Os campos devem ser textos de até 120 caracteres, sem caracteres de controle"), 400
            changes[field] = value.strip()
        expected = data.get("expected_updated_at")
        if expected is not None and not isinstance(expected, str):
            return jsonify(ok=False, error="Versão do cadastro inválida"), 400
        with lock:
            device = devices.get(ip)
            if device is None:
                return jsonify(ok=False, error="Dispositivo não encontrado"), 404
            name = device["name"]
        # Não altera device_state: pings e heartbeats não podem apagar o cadastro.
        with db_connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("""SELECT department, room, responsible, updated_at
                                  FROM device_organization WHERE ip=?""", (ip,)).fetchone()
            current = dict(zip((*FIELDS, "updated_at"), row)) if row else empty_organization()
            if expected is not None and expected != current["updated_at"]:
                return jsonify(ok=False, error="Cadastro alterado em outra sessão. Reabra a máquina antes de salvar."), 409
            updated = {**current, **changes}
            if any(updated[field] != current[field] for field in FIELDS):
                updated["updated_at"] = datetime.now().isoformat()
                conn.execute("""INSERT INTO device_organization
                    (ip, department, room, responsible, updated_at) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(ip) DO UPDATE SET department=excluded.department,
                        room=excluded.room, responsible=excluded.responsible, updated_at=excluded.updated_at
                """, (ip, *(updated[field] for field in FIELDS), updated["updated_at"]))
                description = (f"Cadastro atualizado — Setor: {updated['department'] or 'Não informado'}; "
                               f"Sala: {updated['room'] or 'Não informada'}; "
                               f"Responsável: {updated['responsible'] or 'Não informado'}")
                conn.execute("""INSERT INTO audit_events
                    (timestamp, category, ip, name, status, description)
                    VALUES (?, 'inventario', ?, ?, 'atualizado', ?)""",
                    (updated["updated_at"], ip, name, description))
        return jsonify(ok=True, ip=ip, organization=updated)

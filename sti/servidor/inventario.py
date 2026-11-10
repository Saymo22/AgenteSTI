"""Registro estável de equipamentos, independente da concessão de endereço IP."""
import json
import re
import uuid
import sqlite3
from datetime import datetime

from flask import jsonify, request
from sti.comum.identidade import clean_serial


def uuid_text(value):
    if not isinstance(value, str):
        raise ValueError("UUID inválido")
    parsed = uuid.UUID(value)
    if parsed.int == 0:
        raise ValueError("UUID inválido")
    return str(parsed)


def validate_identity(data):
    if "agent_id" not in data:
        if any(key in data for key in ("instance_id", "hardware_key", "mac_addresses", "serial_number")):
            raise ValueError("Identidade incompleta: agent_id obrigatório")
        return None  # Compatibilidade com os agentes já instalados.
    agent_id = uuid_text(data["agent_id"])
    instance_id = uuid_text(data.get("instance_id"))
    hardware_key = data.get("hardware_key", "")
    if not isinstance(hardware_key, str) or (hardware_key and not re.fullmatch(r"[a-f0-9]{64}", hardware_key)):
        raise ValueError("Referência de hardware inválida")
    profile = {"agent_id": agent_id, "instance_id": instance_id, "hardware_key": hardware_key}
    for key in ("serial_number", "manufacturer", "model"):
        value = data.get(key, "")
        if not isinstance(value, str) or len(value) > 120 or any(ord(c) < 32 for c in value):
            raise ValueError(f"Campo {key} inválido")
        profile[key] = clean_serial(value)
    macs = data.get("mac_addresses", [])
    if not isinstance(macs, list) or len(macs) > 32:
        raise ValueError("Lista de MACs inválida")
    normalized = set()
    for mac in macs:
        if not isinstance(mac, str) or not re.fullmatch(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", mac):
            raise ValueError("Endereço MAC inválido")
        mac = mac.replace("-", ":").upper()
        if mac == "00:00:00:00:00:00" or int(mac[:2], 16) & 1:
            raise ValueError("MAC deve identificar uma interface unicast")
        normalized.add(mac)
    profile["mac_addresses"] = sorted(normalized)
    return profile


def init_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS machine_inventory (
        device_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL UNIQUE,
        hardware_key TEXT NOT NULL DEFAULT '', serial_number TEXT NOT NULL DEFAULT '',
        manufacturer TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
        mac_addresses TEXT NOT NULL DEFAULT '[]', instance_id TEXT NOT NULL,
        current_ip TEXT UNIQUE, last_ip TEXT NOT NULL,
        last_agent_seen TEXT NOT NULL, snapshot TEXT NOT NULL DEFAULT '{}')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS machine_organization (
        device_id TEXT PRIMARY KEY, department TEXT NOT NULL DEFAULT '', room TEXT NOT NULL DEFAULT '',
        responsible TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS identity_conflicts (
        agent_id TEXT NOT NULL, ip TEXT NOT NULL, hardware_key TEXT NOT NULL,
        description TEXT NOT NULL, last_seen TEXT NOT NULL,
        PRIMARY KEY(agent_id, ip, hardware_key))""")
    conn.execute("CREATE TABLE IF NOT EXISTS retired_agent_ids (agent_id TEXT PRIMARY KEY, device_id TEXT NOT NULL)")
    for table, column in (("device_state", "device_id"), ("audit_events", "device_id"), ("command_jobs", "device_id")):
        if column not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_device ON audit_events(device_id, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_hardware ON machine_inventory(hardware_key)")


def record_event(conn, device_id, ip, status, description):
    conn.execute("""INSERT INTO audit_events (timestamp,category,device_id,ip,status,description)
        VALUES (?, 'inventario', ?, ?, ?, ?)""", (datetime.now().isoformat(), device_id, ip, status, description))


def expire_identity_commands(conn, ip, device_id=None):
    # Ações não acompanham a mudança de endereço: devem ser solicitadas novamente.
    conn.execute("""UPDATE command_jobs SET status='expired', updated_at=?, result=?
        WHERE (ip=? OR (device_id IS NOT NULL AND device_id=?)) AND status IN ('queued','delivered','accepted')""",
        (datetime.now().isoformat(), "Identidade ou IP alterado; ação encerrada. Confira o equipamento antes de reenviar.", ip, device_id))


def enroll(conn, ip, profile, threshold):
    """Chamado com lock do inventário + transação IMMEDIATE; nenhum merge por MAC."""
    now = datetime.now()
    agent_id = profile["agent_id"]
    row = conn.execute("""SELECT device_id, current_ip, hardware_key, instance_id, last_agent_seen, snapshot
        FROM machine_inventory WHERE agent_id=?""", (agent_id,)).fetchone()
    reason = ""
    if conn.execute("SELECT 1 FROM retired_agent_ids WHERE agent_id=?", (agent_id,)).fetchone():
        reason = "UUID de instalação substituída. Confira a reinstalação antes de registrar este agente."
    if row:
        if row[2] and profile["hardware_key"] and row[2] != profile["hardware_key"]:
            reason = "Mesmo UUID informado por hardware diferente. Possível clonagem; cadastro preservado."
        elif row[1] != ip and row[3] != profile["instance_id"] and (now - datetime.fromisoformat(row[4])).total_seconds() <= threshold:
            reason = "Mesmo UUID ativo em outro IP por outra instância. Verifique clonagem ou duas cópias do agente."
    if reason:
        previous = conn.execute("SELECT 1 FROM identity_conflicts WHERE agent_id=? AND ip=? AND hardware_key=?",
            (agent_id, ip, profile["hardware_key"])).fetchone()
        conn.execute("INSERT OR REPLACE INTO identity_conflicts VALUES (?,?,?,?,?)",
            (agent_id, ip, profile["hardware_key"], reason, now.isoformat()))
        if not previous:
            record_event(conn, row[0] if row else None, ip, "identidade_conflitante", reason)
        return {"error": reason}
    device_id = row[0] if row else str(uuid.uuid4())
    previous_ip = row[1] if row else None
    occupant = conn.execute("SELECT device_id FROM machine_inventory WHERE current_ip=? AND device_id!=?", (ip, device_id)).fetchone()
    old_state = conn.execute("SELECT device_id FROM device_state WHERE ip=?", (ip,)).fetchone()
    adopt_legacy = not row and not occupant and (old_state is None or not old_state[0])
    if occupant:
        conn.execute("UPDATE machine_inventory SET current_ip=NULL WHERE device_id=?", occupant)
        expire_identity_commands(conn, ip, occupant[0])
        record_event(conn, occupant[0], ip, "ip_liberado", "IP passou a identificar outro equipamento; cadastro e histórico preservados.")
    if previous_ip and previous_ip != ip:
        conn.execute("DELETE FROM device_state WHERE ip=? AND device_id=?", (previous_ip, device_id))
        expire_identity_commands(conn, previous_ip, device_id)
        record_event(conn, device_id, ip, "ip_alterado", f"Endereço alterado de {previous_ip} para {ip}.")
    if not row:
        expire_identity_commands(conn, ip)
        conn.execute("""INSERT INTO machine_inventory
            (device_id,agent_id,instance_id,current_ip,last_ip,last_agent_seen) VALUES (?,?,?,?,?,?)""",
            (device_id, agent_id, profile["instance_id"], None, ip, now.isoformat()))
        record_event(conn, device_id, ip, "identificado", "Identidade permanente registrada pelo agente.")
    if adopt_legacy:
        conn.execute("""INSERT OR IGNORE INTO machine_organization
            SELECT ?,department,room,responsible,updated_at FROM device_organization WHERE ip=?""", (device_id, ip))
        conn.execute("UPDATE audit_events SET device_id=? WHERE ip=? AND device_id IS NULL", (device_id, ip))
    conn.execute("DELETE FROM device_organization WHERE ip=?", (ip,))
    # Não herdar dados de outro ocupante do endereço atual.
    conn.execute("DELETE FROM device_state WHERE ip=? AND (device_id IS NULL OR device_id!=?)", (ip, device_id))
    conn.execute("""UPDATE machine_inventory SET current_ip=?,last_ip=?,instance_id=?,last_agent_seen=?,
        hardware_key=CASE WHEN ?!='' THEN ? ELSE hardware_key END,
        serial_number=CASE WHEN ?!='' THEN ? ELSE serial_number END,
        manufacturer=CASE WHEN ?!='' THEN ? ELSE manufacturer END,
        model=CASE WHEN ?!='' THEN ? ELSE model END, mac_addresses=? WHERE device_id=?""",
        (ip,ip,profile['instance_id'],now.isoformat(),profile['hardware_key'],profile['hardware_key'],
         profile['serial_number'],profile['serial_number'],profile['manufacturer'],profile['manufacturer'],
         profile['model'],profile['model'],json.dumps(profile['mac_addresses']),device_id))
    conn.execute("DELETE FROM identity_conflicts WHERE ip=?", (ip,))
    return {"device_id": device_id, "previous_ip": previous_ip,
            "previous": json.loads(row[5]) if row else {}, "adopt_legacy": adopt_legacy}


def inventory_rows(conn):
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute("SELECT * FROM machine_inventory")]
    conn.row_factory = None
    for row in rows:
        row['mac_addresses'] = json.loads(row['mac_addresses'])
    return rows


def recovery_match(first, second):
    if first.get('hardware_key') and first['hardware_key'] == second.get('hardware_key'):
        return True
    serial = clean_serial(first.get('serial_number'))
    return bool(serial and serial == clean_serial(second.get('serial_number')) and
                set(first.get('mac_addresses', [])) & set(second.get('mac_addresses', [])))


def register_routes(app, require_admin, db_connect, devices, lock, threshold):
    @app.route('/api/inventory/<source_id>/reconcile', methods=['POST'])
    @require_admin
    def reconcile(source_id):
        data = request.get_json(silent=True)
        try:
            source_id = uuid_text(source_id)
            target_id = uuid_text(data.get('target_device_id')) if isinstance(data,dict) else ''
        except ValueError:
            return jsonify(ok=False,error='Identificador inválido'),400
        if not target_id or source_id == target_id:
            return jsonify(ok=False,error='Escolha outro cadastro para recuperar'),400
        with lock:
            with db_connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                records = {r['device_id']:r for r in inventory_rows(conn)}
                source, target = records.get(source_id), records.get(target_id)
                if not source or not target:
                    return jsonify(ok=False,error='Cadastro não encontrado; atualize o painel'),404
                if data.get('expected_agent_id') != source['agent_id']:
                    return jsonify(ok=False,error='A instalação mudou; atualize o painel'),409
                now = datetime.now()
                if not source['current_ip'] or (now-datetime.fromisoformat(source['last_agent_seen'])).total_seconds()>threshold:
                    return jsonify(ok=False,error='O agente da instalação atual deve estar conectado'),409
                if (now-datetime.fromisoformat(target['last_agent_seen'])).total_seconds()<=threshold:
                    return jsonify(ok=False,error='O cadastro anterior ainda recebe dados; não é seguro unir as identidades'),409
                if not recovery_match(source, target):
                    return jsonify(ok=False,error='As referências de hardware não correspondem'),409
                for record in (source,target):
                    expire_identity_commands(conn,record['last_ip'],record['device_id'])
                conn.execute('INSERT OR REPLACE INTO retired_agent_ids VALUES (?,?)',(target['agent_id'],target_id))
                conn.execute('UPDATE retired_agent_ids SET device_id=? WHERE device_id=?',(target_id,source_id))
                conn.execute('DELETE FROM device_state WHERE device_id=?',(target_id,))
                conn.execute('UPDATE device_state SET device_id=? WHERE device_id=?',(target_id,source_id))
                conn.execute('INSERT OR IGNORE INTO machine_organization SELECT ?,department,room,responsible,updated_at FROM machine_organization WHERE device_id=?',(target_id,source_id))
                conn.execute('DELETE FROM machine_organization WHERE device_id=?',(source_id,))
                conn.execute('UPDATE audit_events SET device_id=? WHERE device_id=?',(target_id,source_id))
                saved = json.loads(source['snapshot'])
                saved['device_id'] = target_id
                conn.execute('DELETE FROM machine_inventory WHERE device_id=?',(source_id,))
                conn.execute('''UPDATE machine_inventory SET agent_id=?,hardware_key=?,serial_number=?,manufacturer=?,model=?,
                    mac_addresses=?,instance_id=?,current_ip=?,last_ip=?,last_agent_seen=?,snapshot=? WHERE device_id=?''',
                    (source['agent_id'],source['hardware_key'],source['serial_number'],source['manufacturer'],source['model'],
                     json.dumps(source['mac_addresses']),source['instance_id'],source['current_ip'],source['last_ip'],
                     source['last_agent_seen'],json.dumps(saved),target_id))
                record_event(conn,target_id,source['current_ip'],'instalacao_recuperada',
                    'Reinstalação vinculada pelo administrador; cadastro e histórico anteriores preservados.')
            for ip, device in list(devices.items()):
                if device.get('device_id') == target_id:
                    devices.pop(ip,None)
                elif device.get('device_id') == source_id:
                    device['device_id'] = target_id
        return jsonify(ok=True,device_id=target_id,ip=source['current_ip'])

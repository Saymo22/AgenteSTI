
import os
import time
import json
import hmac
import uuid
import socket
import sqlite3
import secrets
import logging
import threading
import subprocess
import platform
import ipaddress
import re
import math
from collections import defaultdict, deque
from contextlib import contextmanager
from sti.comum.configuracao import BASE_DIR, setting
from sti.servidor import organizacao, inventario, releases
from sti.servidor.identificacao import HostnameResolver

from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    redirect,
    session
)


# ==========================================
# STI COMMAND CENTER - BACKEND V3
# ==========================================

DB_FILE = Path(
    setting(
        "STI_DB_FILE",
        str(BASE_DIR / "monitor.db")
    )
)

NETWORK = ipaddress.ip_network(
    setting(
        "NETWORK",
        "10.2.116.0/22"
    ),
    strict=False
)

SCAN_INTERVAL = max(
    10,
    int(setting("SCAN_INTERVAL", "30"))
)

OFFLINE_THRESHOLD = max(
    30,
    int(setting("OFFLINE_THRESHOLD", "90"))
)

MAX_WORKERS = min(
    100,
    max(
        1,
        int(setting("MAX_WORKERS", "40"))
    )
)

ADMIN_PASSWORD = setting(
    "STI_ADMIN_PASSWORD", ""
)

AGENT_TOKEN = setting(
    "STI_AGENT_TOKEN", ""
)

SECRET_KEY = setting(
    "STI_SECRET_KEY", ""
)

HOST = setting(
    "STI_HOST",
    "127.0.0.1"
)

PORT = int(
    setting(
        "STI_PORT",
        "5000"
    )
)

if NETWORK.version != 4 or NETWORK.num_addresses > 4096:
    raise ValueError("NETWORK deve ser IPv4 e conter no máximo 4096 endereços.")

COMMAND_TTL = max(60, int(setting("COMMAND_TTL", "300")))
COMMAND_RUNNING_TTL = max(COMMAND_TTL, int(setting("COMMAND_RUNNING_TTL", "3600")))
login_attempts = defaultdict(deque)
login_lock = threading.Lock()

app = Flask(__name__)

app.config.update(
    SECRET_KEY=SECRET_KEY or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=(
        setting(
            "STI_HTTPS",
            "false"
        ).lower() == "true"
    ),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=32768
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("STI")

devices = {}

lock = threading.RLock()
scan_lock = threading.Lock()

scan_status = {
    "scanning": False,
    "last_scan": None,
    "progress": 0,
    "total": 0,
    "remapping": False,
    "discovery_generation": 0,
    "last_remap": None,
    "error": None
}


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if not request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================

def agora():
    return datetime.now().isoformat()


def valid_ip(ip):

    try:
        address = ipaddress.ip_address(ip)

        return address.version == 4 and (address.is_loopback or address in NETWORK)

    except ValueError:
        return False


def get_device_online(device):

    last_seen = device.get("last_seen")

    if not isinstance(last_seen, datetime):
        return False

    elapsed = (
        datetime.now() - last_seen
    ).total_seconds()

    return elapsed <= OFFLINE_THRESHOLD


def get_agent_online(device):
    last = device.get("last_agent_seen")
    return (device.get("agent_seen") is True and isinstance(last, datetime)
            and (datetime.now() - last).total_seconds() <= OFFLINE_THRESHOLD)


def identification_source(device):
    if device.get("agent_version") or device.get("agent_seen") or device.get("last_agent_seen"):
        return "agent"
    if device.get("name_source") in ("agent", "dns", "network"):
        return device["name_source"]
    name = device.get("name", "")
    return "network" if not name or name == device.get("ip") or re.fullmatch(r"host-\d+", name) else "saved"


def is_discovery_only(device):
    return not (device.get('device_id') or device.get('hw') or identification_source(device) == 'agent')


def apply_hostname(ip, hostname):
    with lock:
        device = devices.get(ip)
        if not device or identification_source(device) == "agent":
            return  # DNS nunca substitui o nome informado pelo agente autenticado.
        device["name"] = hostname
        device["name_source"] = "dns"
        snapshot = dict(device)
    save_device(ip, snapshot)


hostname_resolver = HostnameResolver(apply_hostname)


def schedule_hostname(ip):
    with lock:
        device = devices.get(ip)
        if not device or identification_source(device) == "agent":
            return
    hostname_resolver.schedule(ip)


def validate_telemetry(data):
    for field in ("name", "user", "os", "agent_version"):
        if field in data and (not isinstance(data[field], str) or len(data[field]) > 120):
            raise ValueError(f"Campo {field} inválido (texto de até 120 caracteres).")
    hw = {}
    for field in ("cpu", "ram_total", "ram_free", "disk_total", "disk_free", "uptime"):
        value = data.get(field)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Campo {field} deve ser numérico.")
            if value < 0 or value > 1e12 or not math.isfinite(value) or (field == "cpu" and value > 100):
                raise ValueError(f"Campo {field} fora da faixa permitida.")
        hw[field] = value
    for kind in ("ram", "disk"):
        total, free = hw[f"{kind}_total"], hw[f"{kind}_free"]
        if total is not None and free is not None and free > total:
            raise ValueError(f"Espaço livre de {kind} maior que o total.")
    printers = data.get("printers", [])
    if not isinstance(printers, list) or len(printers) > 30 or any(
        not isinstance(item, str) or len(item) > 250 for item in printers
    ):
        raise ValueError("Lista de impressoras inválida.")
    hw["printers"] = printers
    capabilities = data.get("capabilities", ["msg"])
    if not isinstance(capabilities, list) or any(
        not isinstance(item, str) or item not in COMMAND_ALLOWED for item in capabilities
    ):
        raise ValueError("Capacidades do agente inválidas.")
    return hw, sorted(set(capabilities))


# ==========================================
# BANCO DE DADOS
# ==========================================

@contextmanager
def db_connect():

    conn = sqlite3.connect(
        str(DB_FILE),
        timeout=15
    )

    conn.execute(
        "PRAGMA busy_timeout=15000"
    )

    conn.execute(
        "PRAGMA journal_mode=WAL"
    )

    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():

    DB_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with db_connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                total INTEGER,
                online INTEGER
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                ip TEXT,
                name TEXT,
                status TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS device_state (
                ip TEXT PRIMARY KEY,
                name TEXT,
                user TEXT,
                os TEXT,
                hw TEXT,
                last_seen TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                category TEXT NOT NULL,
                ip TEXT,
                name TEXT,
                status TEXT NOT NULL,
                description TEXT NOT NULL
            )
        """)

        # Nova tabela de comandos remotos
        conn.execute("""
            CREATE TABLE IF NOT EXISTS command_jobs (
                id TEXT PRIMARY KEY,
                ip TEXT NOT NULL,
                command TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                delivered_at TEXT,
                updated_at TEXT NOT NULL,
                result TEXT NOT NULL DEFAULT ''
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_command_jobs_ip_status
            ON command_jobs(ip, status)
        """)

        # Migração aditiva: preserva bancos e inventários existentes.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(device_state)")}
        for column in ("last_agent_seen", "agent_version", "capabilities", "name_source"):
            if column not in columns:
                conn.execute(f"ALTER TABLE device_state ADD COLUMN {column} TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ip ON audit_events(ip)")
        organizacao.init_schema(conn)
        inventario.init_schema(conn)
        releases.init_schema(conn)

    logger.info(
        "Banco de dados inicializado."
    )


# ==========================================
# AUDITORIA
# ==========================================

_INFER_DEVICE = object()


def audit(
    category,
    status,
    description,
    ip=None,
    name=None,
    device_id=_INFER_DEVICE
):

    try:

        with lock:
            if device_id is _INFER_DEVICE:
                device_id = devices.get(ip, {}).get("device_id")

        with db_connect() as conn:

            conn.execute("""
                INSERT INTO audit_events (
                    timestamp,
                    category,
                    ip,
                    name,
                    status,
                    description, device_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                agora(),
                category,
                ip,
                name,
                status,
                description, device_id
            ))

    except Exception:
        logger.exception(
            "Erro ao registrar auditoria."
        )


# ==========================================
# DISPOSITIVOS - BANCO
# ==========================================

def write_device(conn, ip, device):
    if is_discovery_only(device) and ip not in devices:
        return False  # Uma resolução DNS pendente não recria registros removidos pelo remapeamento.
    device_id = device.get("device_id")
    binding = conn.execute("SELECT device_id FROM machine_inventory WHERE current_ip=?", (ip,)).fetchone()
    if device_id:
        if not binding or binding[0] != device_id:
            return False  # Snapshot de scanner anterior a uma mudança de IP.
    elif binding:
        return False
    result = conn.execute("""INSERT INTO device_state
        (ip,name,user,os,hw,last_seen,last_agent_seen,agent_version,capabilities,name_source,device_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ip) DO UPDATE SET
        name=excluded.name,user=excluded.user,os=excluded.os,hw=excluded.hw,last_seen=excluded.last_seen,
        last_agent_seen=excluded.last_agent_seen,agent_version=excluded.agent_version,
        capabilities=excluded.capabilities,name_source=excluded.name_source,device_id=excluded.device_id
        WHERE excluded.last_seen >= device_state.last_seen""",
        (ip,device.get('name',''),device.get('user',''),device.get('os','Desconhecido'),json.dumps(device.get('hw',{})),
         device['last_seen'].isoformat(),device['last_agent_seen'].isoformat() if device.get('last_agent_seen') else None,
         device.get('agent_version',''),json.dumps(device.get('capabilities',[])),identification_source(device),device_id))
    if not result.rowcount:
        return False
    if device_id:
        conn.execute("UPDATE machine_inventory SET snapshot=? WHERE device_id=? AND current_ip=?",
            (json.dumps(device, default=lambda value: value.isoformat()),device_id,ip))
    return True


def save_device(ip, device):
    try:
        with lock, db_connect() as conn:
            write_device(conn, ip, device)
    except Exception:
        logger.exception("Erro ao salvar dispositivo %s", ip)


def load_devices():

    with db_connect() as conn:

        rows = conn.execute("""
            SELECT
                ip,
                name,
                user,
                os,
                hw,
                last_seen, last_agent_seen, agent_version, capabilities, name_source, device_id
            FROM device_state
        """).fetchall()

    with lock:

        for row in rows:

            ip, name, user, os_name, hw_json, last_seen, agent_last, agent_version, capabilities, name_source, device_id = row

            try:

                last = datetime.fromisoformat(
                    last_seen
                )

                hw = json.loads(hw_json or "{}")
                if not isinstance(hw, dict) or not valid_ip(ip):
                    continue

            except (ValueError, TypeError):
                continue

            devices[ip] = {
                "ip": ip,
                "name": name or ip,
                "name_source": name_source,
                "device_id": device_id,
                "user": user or "",
                "os": os_name or "Desconhecido",
                "hw": hw,
                "latency": None,
                "last_seen": last,
                "online": (
                    (
                        datetime.now() - last
                    ).total_seconds()
                    <= OFFLINE_THRESHOLD
                ),
                "agent_seen": False,
                "last_agent_seen": parse_saved_time(agent_last),
                "agent_version": agent_version or "",
                "capabilities": []
            }

    logger.info(
        "%s dispositivos carregados.",
        len(devices)
    )


# ==========================================
# HISTÓRICO DE STATUS
# ==========================================

def register_change(ip, name, status, device_id=None):

    logger.info(
        "Dispositivo %s: %s",
        ip,
        status
    )

    with db_connect() as conn:

        conn.execute("""
            INSERT INTO events (
                timestamp,
                ip,
                name,
                status
            )
            VALUES (?, ?, ?, ?)
        """, (
            agora(),
            ip,
            name,
            status
        ))

    audit(
        "dispositivo",
        status,
        f"{name} mudou para {status}",
        ip,
        name,
        device_id=device_id
    )


def save_snapshot():

    with lock:

        total = len(devices)

        online = sum(
            1
            for device in devices.values()
            if get_device_online(device)
        )
        active_ids = {device.get('device_id') for device in devices.values()}
        with db_connect() as conn:
            total += sum(row[0] not in active_ids for row in conn.execute('SELECT device_id FROM machine_inventory'))

    with db_connect() as conn:

        conn.execute("""
            INSERT INTO snapshots (
                timestamp,
                total,
                online
            )
            VALUES (?, ?, ?)
        """, (
            agora(),
            total,
            online
        ))


# ==========================================
# AUTENTICAÇÃO
# ==========================================

def require_admin(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if session.get("admin") is not True:

            return jsonify({
                "ok": False,
                "error": "Autenticação necessária"
            }), 401

        if request.method not in ("GET", "HEAD"):

            origin = request.headers.get(
                "Origin"
            )

            if origin and (
                origin.rstrip("/")
                != request.host_url.rstrip("/")
            ):

                return jsonify({
                    "ok": False,
                    "error": "Origem não autorizada"
                }), 403

            if request.headers.get(
                "Sec-Fetch-Site"
            ) == "cross-site":

                return jsonify({
                    "ok": False,
                    "error": "Requisição bloqueada"
                }), 403

        return func(*args, **kwargs)

    return wrapper


def agent_authenticated():

    token = request.headers.get(
        "X-Agent-Token",
        ""
    )

    return (
        bool(AGENT_TOKEN)
        and hmac.compare_digest(
            token.encode("utf-8"),
            AGENT_TOKEN.encode("utf-8")
        )
    )


# ==========================================
# LOGIN ADMINISTRATIVO
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        peer = request.remote_addr or "unknown"
        now = time.monotonic()
        with login_lock:
            for address in list(login_attempts):
                while login_attempts[address] and login_attempts[address][0] <= now - 300:
                    login_attempts[address].popleft()
                if not login_attempts[address]:
                    del login_attempts[address]
            if len(login_attempts[peer]) >= 5:
                return "Muitas tentativas. Aguarde 5 minutos.", 429, {"Retry-After": "300"}
            login_attempts[peer].append(now)

        password = request.form.get(
            "password",
            ""
        )

        if ADMIN_PASSWORD and hmac.compare_digest(
            password.encode("utf-8"),
            ADMIN_PASSWORD.encode("utf-8")
        ):

            with login_lock:
                login_attempts.pop(peer, None)
            session.clear()

            session["admin"] = True

            session.permanent = True

            audit(
                "seguranca",
                "login",
                "Login administrativo realizado"
            )

            return redirect("/")

        audit("seguranca", "login_falhou", "Senha administrativa inválida", ip=peer)

        return "Senha inválida", 401

    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport"
              content="width=device-width, initial-scale=1.0">

        <title>STI | Login</title>

        <style>

            * {
                box-sizing: border-box;
            }

            body {
                margin: 0;
                min-height: 100vh;
                display: grid;
                place-items: center;
                background: #07111f;
                color: white;
                font-family: Arial, sans-serif;
            }

            form {
                width: 350px;
                max-width: 92vw;
                padding: 34px;
                display: grid;
                gap: 18px;
                background: #10223a;
                border: 1px solid #29415c;
                border-radius: 22px;
            }

            h2 {
                margin: 0 0 10px;
            }

            input {
                padding: 15px;
                background: #07111f;
                border: 1px solid #29415c;
                border-radius: 12px;
                color: white;
                outline: none;
            }

            button {
                padding: 15px;
                border: none;
                border-radius: 12px;
                background: #3be4ff;
                color: #07111f;
                font-weight: bold;
                cursor: pointer;
            }

        </style>
    </head>

    <body>

        <form method="POST">

            <h2>STI Command Center</h2>

            <input
                type="password"
                name="password"
                placeholder="Senha administrativa"
                required
            >

            <button type="submit">
                Entrar
            </button>

        </form>

    </body>
    </html>
    """


@app.route("/logout", methods=["POST"])
@require_admin
def logout():

    session.clear()

    return jsonify({
        "ok": True
    })


# ==========================================
# PAINEL PRINCIPAL
# ==========================================

@app.route("/")
def index():

    if not session.get("admin"):

        return redirect("/login")

    return render_template(
        "index.html",
        network=str(NETWORK),
        scan_interval=SCAN_INTERVAL
    )


# ==========================================
# PING
# ==========================================

def parse_saved_time(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except (ValueError, TypeError):
        return None


def ping_host(ip):

    windows = (
        platform.system().lower()
        == "windows"
    )

    command = [
        "ping",
        "-n" if windows else "-c",
        "1",
        "-w" if windows else "-W",
        "800" if windows else "1",
        ip
    ]

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=3
        )

        if result.returncode != 0 or not re.search(r"ttl[=\s]", result.stdout, re.IGNORECASE):

            return False, 0

        match = re.search(
            r"(?:tempo|time)\s*[=<]\s*([\d.,]+)\s*ms",
            result.stdout,
            re.IGNORECASE
        )

        latency = (
            float(
                match.group(1).replace(",", ".")
            )
            if match
            else None
        )

        return True, latency

    except Exception:

        return False, 0


# ==========================================
# SCANNER DE REDE
# ==========================================

def scan_network():

    if not scan_lock.acquire(
        blocking=False
    ):

        return False

    return scan_network_locked()


def discovery_remap_preview():
    with lock, db_connect() as conn:
        targets = {ip: device for ip, device in devices.items() if is_discovery_only(device)}
        represented_ids = {device.get('device_id') for device in devices.values()}
        archived = sum(row[0] not in represented_ids for row in conn.execute('SELECT device_id FROM machine_inventory'))
        online = sum(get_device_online(device) for device in targets.values())
        return {
            'removed': len(targets),
            'online_removed': online,
            'offline_removed': len(targets) - online,
            'kept': len(devices) - len(targets) + archived,
            'network': str(NETWORK),
        }


def clear_discovery_devices():
    with lock:
        targets = [ip for ip, device in devices.items() if is_discovery_only(device)]
        with db_connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            for ip in targets:
                conn.execute("DELETE FROM device_state WHERE ip=? AND COALESCE(device_id,'')=''", (ip,))
                inventario.expire_identity_commands(conn, ip)
            conn.execute('''INSERT INTO audit_events (timestamp, category, status, description)
                VALUES (?, 'scanner', 'remapeado', ?)''',
                (agora(), f'Remapeamento da rede {NETWORK}: {len(targets)} registros sem agente removidos. Nova varredura iniciada.'))
        for ip in targets:
            devices.pop(ip, None)
        hostname_resolver.forget(targets)
        scan_status['discovery_generation'] += 1
        return len(targets)


def scan_network_locked(remap=False):
    try:

        if remap:
            removed = clear_discovery_devices()
            with lock:
                scan_status['last_remap'].update(removed=removed, status='scanning')

        hosts = [
            str(ip)
            for ip in NETWORK.hosts()
        ]

        with lock:

            scan_status.update(
                scanning=True,
                progress=0,
                total=len(hosts),
                error=None
            )

        found = {}

        with ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as executor:

            futures = {
                executor.submit(
                    ping_host,
                    ip
                ): ip
                for ip in hosts
            }

            for index, future in enumerate(
                as_completed(futures),
                1
            ):

                ip = futures[future]

                online, latency = future.result()

                if online:
                    found[ip] = latency

                with lock:
                    scan_status["progress"] = index

        now = datetime.now()

        changes = []
        to_save = []

        with lock:

            for ip, device in devices.items():

                if ip in found:

                    was_online = device.get("online", False)

                    if not was_online:
                        changes.append((
                            ip,
                            device["name"],
                            "online", device.get('device_id')
                        ))

                    device["online"] = True
                    device["latency"] = found[ip]
                    device["last_ping_seen"] = now
                    device["last_seen"] = max(now, device["last_seen"])

                    to_save.append((
                        ip,
                        dict(device)
                    ))

                else:

                    elapsed = (
                        now - device["last_seen"]
                    ).total_seconds()

                    if (
                        elapsed > OFFLINE_THRESHOLD
                        and device.get("online", True)
                    ):

                        device["online"] = False

                        changes.append((
                            ip,
                            device["name"],
                            "offline", device.get('device_id')
                        ))

            for ip, latency in found.items():

                if ip not in devices:

                    name = (
                        ip
                    )

                    device = {
                        "ip": ip,
                        "name": name,
                        "name_source": "network",
                        "user": "Não informado",
                        "os": "Desconhecido",
                        "hw": {},
                        "latency": latency,
                        "last_ping_seen": now,
                        "online": True,
                        "last_seen": now,
                        "agent_seen": False
                    }

                    devices[ip] = device

                    to_save.append((
                        ip,
                        dict(device)
                    ))

            scan_status.update(
                scanning=False,
                progress=len(hosts),
                last_scan=now.isoformat()
            )

        for ip, device in to_save:
            save_device(ip, device)

        for ip in found:
            schedule_hostname(ip)

        for ip, name, status, device_id in changes:
            register_change(
                ip,
                name,
                status, device_id
            )

        save_snapshot()

        if remap:
            with lock:
                scan_status['last_remap'].update(status='completed', completed_at=agora())

        return True

    except Exception:

        with lock:
            scan_status['error'] = 'Não foi possível concluir a varredura. Tente escanear a rede novamente.'
            if remap:
                scan_status['last_remap']['status'] = 'error'

        logger.exception(
            "Erro durante o scanner."
        )

        audit(
            "scanner",
            "erro",
            "Falha no escaneamento"
        )

        return False

    finally:

        with lock:
            scan_status["scanning"] = False
            scan_status['remapping'] = False

        scan_lock.release()


def start_network_scan(remap=False):
    if not scan_lock.acquire(blocking=False):
        return False
    with lock:
        scan_status.update(scanning=True, remapping=remap, progress=0, total=len(list(NETWORK.hosts())), error=None)
        if remap:
            scan_status['last_remap'] = {'id': str(uuid.uuid4()), 'status': 'queued', 'removed': 0, 'started_at': agora()}
    try:
        threading.Thread(target=scan_network_locked, kwargs={'remap': remap}, daemon=True, name='STI-network-scan').start()
    except Exception:
        with lock:
            scan_status.update(scanning=False, remapping=False)
            if remap:
                scan_status['last_remap']['status'] = 'error'
        scan_lock.release()
        raise
    return True


def scanner_loop():

    while True:

        scan_network()

        time.sleep(SCAN_INTERVAL)


# ==========================================
# API DE DISPOSITIVOS
# ==========================================

@app.route("/api/devices")
@require_admin
def api_devices():
    now = datetime.now()
    with lock:
        organizations = organizacao.load_organizations(db_connect)
        with db_connect() as conn:
            registered = inventario.inventory_rows(conn)
            conflicts = conn.execute("SELECT agent_id,ip,description,last_seen FROM identity_conflicts WHERE last_seen>=? ORDER BY last_seen DESC LIMIT 50",((now-timedelta(days=1)).isoformat(),)).fetchall()
        profiles = {row['device_id']:row for row in registered}
        by_hardware = defaultdict(list)
        by_serial = defaultdict(list)
        for row in registered:
            row['saved'] = json.loads(row['snapshot'])
            if row['hardware_key']:
                by_hardware[row['hardware_key']].append(row)
            if row['serial_number']:
                by_serial[row['serial_number']].append(row)
        candidates = list(devices.values())
        active_ids = {d.get('device_id') for d in candidates}
        for row in registered:
            if row['device_id'] not in active_ids:
                saved = dict(row['saved'])
                if not saved:
                    continue
                saved.update(device_id=row['device_id'], ip=row['last_ip'],address_active=False,
                    last_seen=parse_saved_time(saved.get('last_seen')),
                    last_agent_seen=parse_saved_time(saved.get('last_agent_seen')),
                    agent_seen=False,latency=None)
                candidates.append(saved)
        items = []
        for device in candidates:
            elapsed = max(0, (now-device['last_seen']).total_seconds())
            device_id = device.get('device_id')
            profile = profiles.get(device_id, {})
            active = device.get('address_active', True) and (not device_id or profile.get('current_ip') == device['ip'])
            online = active and elapsed <= OFFLINE_THRESHOLD
            last_ping = device.get('last_ping_seen')
            if not isinstance(last_ping,datetime):
                last_ping = parse_saved_time(last_ping)
            possible = {r['device_id']:r for r in [*by_hardware.get(profile.get('hardware_key'),[]), *by_serial.get(profile.get('serial_number'),[])]}
            items.append({
                'ip':device['ip'],'device_id':device_id,'address_active':bool(active),
                'name':device['name'],'user':device['user'],'os':device['os'],'hw':device.get('hw',{}),
                'organization':organizations.get(device_id or device['ip'],organizacao.empty_organization()),
                'agent_online':bool(active and get_agent_online(device)),
                'agent_version':device.get('agent_version',''),'capabilities':device.get('capabilities',[]),
                'last_agent_seen':device['last_agent_seen'].isoformat() if device.get('last_agent_seen') else None,
                'identification_source':identification_source(device),
                'latency':device.get('latency') if online and last_ping and (now-last_ping).total_seconds() <= OFFLINE_THRESHOLD else None,
                'last_ping_seen':last_ping.isoformat() if last_ping else None,'seconds_ago':int(elapsed),'online':bool(online),
                'agent_id':profile.get('agent_id',''),'serial_number':profile.get('serial_number',''),
                'mac_addresses':profile.get('mac_addresses',[]),'manufacturer':profile.get('manufacturer',''),'model':profile.get('model',''),
                'recovery_candidates':[{'device_id':r['device_id'],'name':r['saved'].get('name',r['last_ip']),
                    'ip':r['last_ip'],'organization':organizations.get(r['device_id'],organizacao.empty_organization())} for r in possible.values() if device_id and r['device_id']!=device_id and inventario.recovery_match(profile,r) and
                    (now-datetime.fromisoformat(r['last_agent_seen'])).total_seconds()>OFFLINE_THRESHOLD]
            })
        status = dict(scan_status)
    items.sort(key=lambda d:(not d['online'],ipaddress.ip_address(d['ip']),d.get('device_id') or ''))
    online = sum(d['online'] for d in items)
    return jsonify(devices=items,summary={'total':len(items),'online':online,'offline':len(items)-online},scan=status,
        identity_conflicts=[dict(zip(('agent_id','ip','description','last_seen'),row)) for row in conflicts])


# ==========================================
# COMANDOS REMOTOS V2
# ==========================================

COMMAND_ALLOWED = {
    "restart",
    "shutdown",
    "msg"
}

COMMAND_TRANSITIONS = {
    "delivered": {
        "accepted",
        "rejected",
        "failed"
    },

    "accepted": {
        "completed",
        "rejected",
        "failed",
        "initiated"
    }
}


# ==========================================
# CRIAR COMANDO
# ==========================================

def expire_commands(conn):
    now = datetime.now()
    rows = conn.execute("""
        SELECT id, ip, command, status, device_id FROM command_jobs
        WHERE (status IN ('queued', 'delivered') AND requested_at < ?)
           OR (status = 'accepted' AND updated_at < ?)
    """, ((now - timedelta(seconds=COMMAND_TTL)).isoformat(),
          (now - timedelta(seconds=COMMAND_RUNNING_TTL)).isoformat())).fetchall()
    for job_id, ip, command, status, device_id in rows:
        result = "Prazo excedido; execução não confirmada. Confira a máquina antes de reenviar."
        conn.execute("UPDATE command_jobs SET status='expired', result=?, updated_at=? WHERE id=?",
                     (result, now.isoformat(), job_id))
        conn.execute("""INSERT INTO audit_events
            (timestamp, category, ip, status, description, device_id) VALUES (?, 'comando', ?, 'expired', ?, ?)""",
            (now.isoformat(), ip, f"{command}: {result} ID: {job_id}",device_id))


def create_command(
    ip,
    command,
    message="",
    device_id=None
):

    job_id = str(uuid.uuid4())

    timestamp = agora()

    with db_connect() as conn:

        conn.execute("BEGIN IMMEDIATE")
        expire_commands(conn)

        existing = conn.execute("""
            SELECT id
            FROM command_jobs
            WHERE ip = ?
              AND status IN (
                  'queued',
                  'delivered',
                  'accepted'
              )
            LIMIT 1
        """, (ip,)).fetchone()

        if existing:
            return None

        conn.execute("""
            INSERT INTO command_jobs (
                id,
                ip,
                command,
                message,
                status,
                requested_by,
                requested_at,
                updated_at, device_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            ip,
            command,
            message,
            "queued",
            "admin",
            timestamp,
            timestamp, device_id
        ))

    audit(
        "comando",
        "pendente",
        f"Comando {command} solicitado. ID: {job_id}",
        ip
    )

    return job_id


# ==========================================
# ENTREGAR COMANDO AO AGENTE
# ==========================================

def deliver_command(ip, device_id=None):

    timestamp = agora()

    with db_connect() as conn:

        conn.execute("BEGIN IMMEDIATE")
        expire_commands(conn)

        row = conn.execute("""
            SELECT id, command, message, status
            FROM command_jobs
            WHERE ip = ?
              AND COALESCE(device_id,'') = COALESCE(?,'')
              AND status IN ('queued', 'delivered')
            ORDER BY requested_at ASC
            LIMIT 1
        """, (ip,device_id)).fetchone()

        if not row:
            return None

        job_id, command, message, previous_status = row

        conn.execute("""
            UPDATE command_jobs
            SET status = 'delivered',
                delivered_at = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            timestamp,
            timestamp,
            job_id
        ))

    if previous_status == "queued":
        audit("comando", "entregue", f"Comando {command} entregue. ID: {job_id}", ip)

    return {
        "id": job_id,
        "command": command,
        "message": message
    }


# ==========================================
# CONSULTAR COMANDO
# ==========================================

def get_command(job_id):

    with db_connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        expire_commands(conn)
        row = conn.execute("""
            SELECT
                id,
                ip,
                command,
                status,
                requested_by,
                requested_at,
                delivered_at,
                updated_at,
                result
            FROM command_jobs
            WHERE id = ?
        """, (
            job_id,
        )).fetchone()

    if not row:
        return None

    columns = [
        "id",
        "ip",
        "command",
        "status",
        "requested_by",
        "requested_at",
        "delivered_at",
        "updated_at",
        "result"
    ]

    return dict(
        zip(columns, row)
    )


# ==========================================
# API DO AGENTE
# ==========================================

@app.route(
    "/api/agent",
    methods=["POST"]
)
def api_agent():
    if not agent_authenticated():
        return jsonify(ok=False, error="Token inválido"), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(ok=False, error="JSON inválido"), 400
    ip = request.remote_addr
    if not valid_ip(ip):
        return jsonify(ok=False, error="IP não autorizado"), 403
    try:
        hw, capabilities = validate_telemetry(data)
        profile = inventario.validate_identity(data)
        update_report = releases.validate_update_status(data)
    except (ValueError, AttributeError) as error:
        return jsonify(ok=False, error=str(error)), 400
    now = datetime.now()
    with lock:
        address_device = devices.get(ip, {})
        registration = None
        with db_connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if profile:
                registration = inventario.enroll(conn, ip, profile, OFFLINE_THRESHOLD)
                if registration.get('error'):
                    return jsonify(ok=False, code='identity_conflict', error=registration['error']), 409
                previous_ip = registration['previous_ip']
                old = devices.get(previous_ip, {}) if previous_ip else {}
                if old.get('device_id') != registration['device_id']:
                    old = registration['previous']
                    for field in ('last_seen', 'last_agent_seen'):
                        old[field] = parse_saved_time(old.get(field))
                if registration['adopt_legacy']:
                    old = address_device
            else:
                if conn.execute("SELECT 1 FROM machine_inventory WHERE current_ip=?", (ip,)).fetchone():
                    return jsonify(ok=False, code='identity_required', error="Este equipamento já usa identidade permanente. Atualize o agente."), 409
                old = address_device
            last = old.get('last_seen')
            was_offline = isinstance(last, datetime) and (now-last).total_seconds() > OFFLINE_THRESHOLD
            device = {
                'ip':ip, 'device_id':registration['device_id'] if registration else None,
                'name':str(data.get('name') or old.get('name') or ip)[:120], 'name_source':'agent',
                'user':str(data['user'] if 'user' in data else old.get('user',''))[:120],
                'os':data.get('os') or old.get('os') or 'Desconhecido',
                'agent_version':data.get('agent_version','legado'), 'capabilities':capabilities,
                'last_agent_seen':now,'hw':hw,'latency':address_device.get('latency'),
                'last_ping_seen':address_device.get('last_ping_seen'),
                'last_seen':now,'online':True,'agent_seen':True,
            }
            write_device(conn, ip, device)
            releases.record_heartbeat(conn, device.get('device_id'), device['agent_version'], update_report)
            update = releases.update_offer(conn, device.get('device_id'), device['agent_version'], update_report[0])
        if registration and registration['previous_ip'] != ip:
            previous_ip = registration['previous_ip']
            if devices.get(previous_ip, {}).get('device_id') == device['device_id']:
                devices.pop(previous_ip, None)
        devices[ip] = device
        if was_offline:
            register_change(ip, device['name'], 'online', device.get('device_id'))
        job = deliver_command(ip, device.get('device_id'))
    return jsonify(ok=True, device_id=device.get('device_id'), update=update,
        command_id=job['id'] if job else None, command=job['command'] if job else None,
        message=job['message'] if job else None)



# ==========================================
# API DE ENVIO DE COMANDOS
# ==========================================

@app.route(
    "/api/command/<ip>",
    methods=["POST"]
)
@require_admin
def api_command(ip):

    if not valid_ip(ip):

        return jsonify({
            "ok": False,
            "error": "IP inválido"
        }), 400

    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):

        return jsonify({
            "ok": False,
            "error": "JSON inválido"
        }), 400

    command = str(
        data.get("command", "")
    ).strip()

    if command not in COMMAND_ALLOWED:

        return jsonify({
            "ok": False,
            "error": "Comando não permitido"
        }), 400

    message = str(
        data.get("message") or ""
    ).strip()
    if len(message) > 500:
        return jsonify(ok=False, error="Mensagem limitada a 500 caracteres"), 400

    if command == "msg" and not message:

        return jsonify({
            "ok": False,
            "error": "Mensagem obrigatória"
        }), 400

    with lock:

        device = devices.get(ip)

        if not device:

            return jsonify({
                "ok": False,
                "error": "Dispositivo não encontrado"
            }), 404

        if not device.get("agent_seen"):

            return jsonify({
                "ok": False,
                "error": "Agente não autenticado"
            }), 409

        if not get_agent_online(device):

            return jsonify({
                "ok": False,
                "error": "Agente indisponível"
            }), 409

        if command not in device.get("capabilities", ["msg"]):
            return jsonify(ok=False, error="Comando não habilitado neste agente"), 409

        if device.get('device_id') and data.get('device_id') != device['device_id']:
            return jsonify(ok=False, error="Identidade alterada. Atualize o painel antes de enviar a ação."), 409

        job_id = create_command(ip, command, message, device.get('device_id'))

    if job_id is None:

        return jsonify({
            "ok": False,
            "error": "Já existe comando em andamento"
        }), 409

    return jsonify({
        "ok": True,
        "command_id": job_id,
        "status": "queued",
        "executed": False
    }), 202


# ==========================================
# AGENTE CONFIRMA STATUS
# ==========================================

@app.route(
    "/api/agent/command-status",
    methods=["POST"]
)
def api_command_status():

    if not agent_authenticated():

        return jsonify({
            "ok": False,
            "error": "Token inválido"
        }), 401

    ip = request.remote_addr

    if not valid_ip(ip):

        return jsonify({
            "ok": False,
            "error": "IP não autorizado"
        }), 403

    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):

        return jsonify({
            "ok": False,
            "error": "JSON inválido"
        }), 400

    job_id = str(
        data.get("id", "")
    ).strip()

    status = str(
        data.get("status", "")
    ).strip()

    result = str(
        data.get("result", "")
    )[:500]

    allowed_statuses = {
        "accepted",
        "rejected",
        "completed",
        "failed",
        "initiated"
    }

    if (
        not job_id
        or status not in allowed_statuses
    ):

        return jsonify({
            "ok": False,
            "error": "Dados inválidos"
        }), 400

    timestamp = agora()

    with db_connect() as conn:

        conn.execute("BEGIN IMMEDIATE")
        expire_commands(conn)

        row = conn.execute("""
            SELECT status, command, device_id
            FROM command_jobs
            WHERE id = ?
              AND ip = ?
        """, (
            job_id,
            ip
        )).fetchone()

        if not row:

            return jsonify({
                "ok": False,
                "error": "Comando não encontrado"
            }), 404

        previous, command, job_device_id = row
        if job_device_id:
            binding = conn.execute("SELECT agent_id,instance_id,hardware_key FROM machine_inventory WHERE device_id=? AND current_ip=?", (job_device_id,ip)).fetchone()
            if (not binding or data.get('agent_id') != binding[0] or data.get('instance_id') != binding[1]
                    or (binding[2] and data.get('hardware_key') != binding[2])):
                return jsonify(ok=False,error="A identidade não corresponde ao destinatário do comando"), 409

        # Confirmação repetida
        if previous == status:

            return jsonify({
                "ok": True,
                "status": status
            })

        allowed_next = COMMAND_TRANSITIONS.get(
            previous,
            set()
        )

        if status not in allowed_next:

            return jsonify({
                "ok": False,
                "error": "Transição inválida"
            }), 409

        conn.execute("""
            UPDATE command_jobs
            SET status = ?,
                result = ?,
                updated_at = ?
            WHERE id = ?
              AND ip = ?
        """, (
            status,
            result,
            timestamp,
            job_id,
            ip
        ))

    audit(
        "comando",
        status,
        f"{command}: {result or status}. ID: {job_id}",
        ip
    )

    return jsonify({
        "ok": True,
        "status": status
    })


# ==========================================
# CONSULTA DO STATUS DO COMANDO
# ==========================================

@app.route(
    "/api/commands/<job_id>",
    methods=["GET"]
)
@require_admin
def api_get_command(job_id):

    command = get_command(
        job_id
    )

    if command is None:

        return jsonify({
            "ok": False,
            "error": "Comando não encontrado"
        }), 404

    return jsonify({
        "ok": True,
        "job": command
    })


# ==========================================
# ESCANEAR REDE MANUALMENTE
# ==========================================

@app.route(
    "/api/scan",
    methods=["POST"]
)
@require_admin
def api_scan():

    try:
        started = start_network_scan()
    except (RuntimeError, OSError):
        logger.exception('Não foi possível iniciar o scanner.')
        return jsonify(ok=False, error='Não foi possível iniciar a varredura. Tente novamente.'), 503

    if not started:

        return jsonify({
            "ok": False,
            "error": "Scan já em andamento"
        }), 409

    audit(
        "scanner",
        "solicitado",
        "Escaneamento manual solicitado"
    )

    return jsonify({
        "ok": True,
        "status": "iniciado"
    }), 202


@app.route('/api/remap', methods=['GET', 'POST'])
@require_admin
def api_remap():
    if request.method == 'GET':
        return jsonify(ok=True, **discovery_remap_preview())
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('confirm') is not True:
        return jsonify(ok=False, error='Confirme a limpeza dos registros sem agente.'), 400
    try:
        started = start_network_scan(remap=True)
    except (RuntimeError, OSError):
        logger.exception('Não foi possível iniciar o remapeamento.')
        return jsonify(ok=False, error='Não foi possível iniciar o remapeamento. Tente novamente.'), 503
    if not started:
        return jsonify(ok=False, error='Aguarde a varredura atual terminar antes de remapear.'), 409
    with lock:
        return jsonify(ok=True, remap_id=scan_status['last_remap']['id'], scan=dict(scan_status)), 202


# ==========================================
# HISTÓRICO DE DISPONIBILIDADE
# ==========================================

@app.route("/api/history")
@require_admin
def api_history():

    with db_connect() as conn:

        rows = conn.execute("""
            SELECT
                timestamp,
                online,
                total
            FROM snapshots
            ORDER BY id DESC
            LIMIT 300
        """).fetchall()

    return jsonify({
        "snapshots": rows[::-1]
    })


# ==========================================
# HISTÓRICO DE EVENTOS
# ==========================================

@app.route("/api/events")
@require_admin
def api_events():

    try:

        limit = min(
            500,
            max(
                1,
                int(
                    request.args.get(
                        "limit",
                        "100"
                    )
                )
            )
        )

    except ValueError:

        return jsonify({
            "ok": False,
            "error": "Limite inválido"
        }), 400

    ip = request.args.get(
        "ip",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    query = """
        SELECT
            timestamp,
            category,
            ip,
            name,
            status,
            description, device_id
        FROM audit_events
        WHERE 1=1
    """

    params = []

    device_id = request.args.get('device_id','').strip()
    if device_id:
        try:
            device_id = inventario.uuid_text(device_id)
        except ValueError:
            return jsonify(ok=False,error='Identificador inválido'),400
        query += ' AND device_id = ?'
        params.append(device_id)

    if ip:

        if not valid_ip(ip):

            return jsonify({
                "ok": False,
                "error": "IP inválido"
            }), 400

        query += " AND ip = ?"
        params.append(ip)

    if category:

        query += " AND category = ?"
        params.append(category)

    query += """
        ORDER BY id DESC
        LIMIT ?
    """

    params.append(limit)

    with db_connect() as conn:

        rows = conn.execute(
            query,
            params
        ).fetchall()

    columns = [
        "timestamp",
        "category",
        "ip",
        "name",
        "status",
        "description", "device_id"
    ]

    events = [
        dict(zip(columns, row))
        for row in rows
    ]

    return jsonify({
        "events": events
    })



# ==========================================
# STI - MÓDULO DE RELATÓRIOS
# ==========================================

from sti.servidor.relatorios import registrar_relatorios

registrar_relatorios(
    app,
    require_admin,
    db_connect
)

organizacao.register_routes(app, require_admin, db_connect, devices, lock, valid_ip)
inventario.register_routes(app, require_admin, db_connect, devices, lock, OFFLINE_THRESHOLD)
releases.register_routes(app, require_admin, db_connect, lambda: DB_FILE, agent_authenticated, valid_ip)


# ==========================================
# INICIALIZAÇÃO
# ==========================================

startup_lock = threading.Lock()
initialized = False
scanner_started = False


def create_app(start_scanner=True):
    """Inicialização explícita para execução direta ou WSGI, em um só processo."""
    global initialized, scanner_started

    if not all((
        ADMIN_PASSWORD,
        AGENT_TOKEN,
        SECRET_KEY
    )):

        raise SystemExit(
            "Configure STI_ADMIN_PASSWORD, "
            "STI_AGENT_TOKEN e STI_SECRET_KEY."
        )

    with startup_lock:
        if not initialized:
            init_db()
            load_devices()
            initialized = True
        if start_scanner and not scanner_started:
            threading.Thread(target=scanner_loop, daemon=True, name="STI-Scanner").start()
            scanner_started = True
    return app


def main():
    create_app()

    logger.info(
        "STI Command Center V3 iniciado."
    )

    logger.info(
        "Rede monitorada: %s",
        NETWORK
    )

    from waitress import serve
    serve(app, host=HOST, port=PORT, threads=8)


if __name__ == "__main__":
    main()

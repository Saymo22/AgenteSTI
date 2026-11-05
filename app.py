
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

BASE_DIR = Path(__file__).resolve().parent

DB_FILE = Path(
    os.environ.get(
        "STI_DB_FILE",
        str(BASE_DIR / "monitor.db")
    )
)

NETWORK = ipaddress.ip_network(
    os.environ.get(
        "NETWORK",
        "10.2.116.0/22"
    ),
    strict=False
)

SCAN_INTERVAL = max(
    10,
    int(os.environ.get("SCAN_INTERVAL", "30"))
)

OFFLINE_THRESHOLD = max(
    30,
    int(os.environ.get("OFFLINE_THRESHOLD", "90"))
)

MAX_WORKERS = min(
    100,
    max(
        1,
        int(os.environ.get("MAX_WORKERS", "40"))
    )
)

ADMIN_PASSWORD = os.environ.get(
    "STI_ADMIN_PASSWORD", ""
)

AGENT_TOKEN = os.environ.get(
    "STI_AGENT_TOKEN", ""
)

SECRET_KEY = os.environ.get(
    "STI_SECRET_KEY", ""
)

HOST = os.environ.get(
    "STI_HOST",
    "127.0.0.1"
)

PORT = int(
    os.environ.get(
        "STI_PORT",
        "5000"
    )
)

app = Flask(__name__)

app.config.update(
    SECRET_KEY=SECRET_KEY or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=(
        os.environ.get(
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
    "total": 0
}


# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================

def agora():
    return datetime.now().isoformat()


def valid_ip(ip):

    try:
        address = ipaddress.ip_address(ip)

        # Permite testes locais no mesmo computador
        if address.is_loopback:
            return True

        return (
            address.version == 4
            and address in NETWORK
        )

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


# ==========================================
# BANCO DE DADOS
# ==========================================

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

    return conn


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

    logger.info(
        "Banco de dados inicializado."
    )


# ==========================================
# AUDITORIA
# ==========================================

def audit(
    category,
    status,
    description,
    ip=None,
    name=None
):

    try:

        with db_connect() as conn:

            conn.execute("""
                INSERT INTO audit_events (
                    timestamp,
                    category,
                    ip,
                    name,
                    status,
                    description
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                agora(),
                category,
                ip,
                name,
                status,
                description
            ))

    except Exception:
        logger.exception(
            "Erro ao registrar auditoria."
        )


# ==========================================
# DISPOSITIVOS - BANCO
# ==========================================

def save_device(ip, device):

    try:

        with db_connect() as conn:

            conn.execute("""
                INSERT OR REPLACE INTO device_state (
                    ip,
                    name,
                    user,
                    os,
                    hw,
                    last_seen
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                ip,
                device.get("name", ""),
                device.get("user", ""),
                device.get("os", "Desconhecido"),
                json.dumps(
                    device.get("hw", {})
                ),
                device["last_seen"].isoformat()
            ))

    except Exception:
        logger.exception(
            "Erro ao salvar dispositivo %s",
            ip
        )


def load_devices():

    with db_connect() as conn:

        rows = conn.execute("""
            SELECT
                ip,
                name,
                user,
                os,
                hw,
                last_seen
            FROM device_state
        """).fetchall()

    with lock:

        for row in rows:

            ip, name, user, os_name, hw_json, last_seen = row

            try:

                last = datetime.fromisoformat(
                    last_seen
                )

                hw = json.loads(
                    hw_json or "{}"
                )

            except (ValueError, TypeError):
                continue

            devices[ip] = {
                "ip": ip,
                "name": name or ip,
                "user": user or "",
                "os": os_name or "Desconhecido",
                "hw": hw,
                "latency": 0,
                "last_seen": last,
                "online": (
                    (
                        datetime.now() - last
                    ).total_seconds()
                    <= OFFLINE_THRESHOLD
                ),
                "agent_seen": False
            }

    logger.info(
        "%s dispositivos carregados.",
        len(devices)
    )


# ==========================================
# HISTÓRICO DE STATUS
# ==========================================

def register_change(ip, name, status):

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
        name
    )


def save_snapshot():

    with lock:

        total = len(devices)

        online = sum(
            1
            for device in devices.values()
            if get_device_online(device)
        )

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
            token,
            AGENT_TOKEN
        )
    )


# ==========================================
# LOGIN ADMINISTRATIVO
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        password = request.form.get(
            "password",
            ""
        )

        if ADMIN_PASSWORD and hmac.compare_digest(
            password,
            ADMIN_PASSWORD
        ):

            session.clear()

            session["admin"] = True

            session.permanent = True

            audit(
                "seguranca",
                "login",
                "Login administrativo realizado"
            )

            return redirect("/")

        time.sleep(0.3)

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

        if result.returncode != 0:

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
            else 0
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

    try:

        hosts = [
            str(ip)
            for ip in NETWORK.hosts()
        ]

        with lock:

            scan_status.update(
                scanning=True,
                progress=0,
                total=len(hosts)
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

                    was_online = get_device_online(
                        device
                    )

                    if not was_online:
                        changes.append((
                            ip,
                            device["name"],
                            "online"
                        ))

                    device["online"] = True
                    device["latency"] = found[ip]
                    device["last_seen"] = now

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
                            "offline"
                        ))

            for ip, latency in found.items():

                if ip not in devices:

                    name = (
                        f"host-{ip.split('.')[-1]}"
                    )

                    device = {
                        "ip": ip,
                        "name": name,
                        "user": "Não informado",
                        "os": "Desconhecido",
                        "hw": {},
                        "latency": latency,
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

        for ip, name, status in changes:
            register_change(
                ip,
                name,
                status
            )

        save_snapshot()

        return True

    except Exception:

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

        scan_lock.release()


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

        items = []

        for device in devices.values():

            elapsed = (
                now - device["last_seen"]
            ).total_seconds()

            items.append({
                "ip": device["ip"],
                "name": device["name"],
                "user": device["user"],
                "os": device["os"],
                "hw": device.get("hw", {}),
                "latency": device.get("latency", 0),
                "seconds_ago": int(
                    max(0, elapsed)
                ),
                "online": (
                    elapsed <= OFFLINE_THRESHOLD
                )
            })

        status = dict(scan_status)

    items.sort(
        key=lambda item: (
            not item["online"],
            ipaddress.ip_address(item["ip"])
        )
    )

    online = sum(
        1
        for item in items
        if item["online"]
    )

    return jsonify({
        "devices": items,

        "summary": {
            "total": len(items),
            "online": online,
            "offline": len(items) - online
        },

        "scan": status
    })


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

def create_command(
    ip,
    command,
    message=""
):

    job_id = str(uuid.uuid4())

    timestamp = agora()

    with db_connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

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
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            ip,
            command,
            message,
            "queued",
            "admin",
            timestamp,
            timestamp
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

def deliver_command(ip):

    timestamp = agora()

    with db_connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute("""
            SELECT id, command, message
            FROM command_jobs
            WHERE ip = ?
              AND status = 'queued'
            ORDER BY requested_at ASC
            LIMIT 1
        """, (ip,)).fetchone()

        if not row:
            return None

        job_id, command, message = row

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

    audit(
        "comando",
        "entregue",
        f"Comando {command} entregue. ID: {job_id}",
        ip
    )

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

        return jsonify({
            "ok": False,
            "error": "Token inválido"
        }), 401

    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):

        return jsonify({
            "ok": False,
            "error": "JSON inválido"
        }), 400

    ip = request.remote_addr

    if not valid_ip(ip):

        return jsonify({
            "ok": False,
            "error": "IP não autorizado"
        }), 403

    now = datetime.now()

    with lock:

        old = devices.get(
            ip,
            {}
        )

        name = str(
            data.get("name")
            or old.get("name")
            or ip
        )[:120]

        user = str(
            data.get("user")
            or old.get("user")
            or ""
        )[:120]

        hw = {
            key: data.get(key)
            for key in (
                "cpu",
                "ram_total",
                "ram_free",
                "disk_total",
                "disk_free",
                "uptime",
                "printers"
            )
        }

        previous_seen = old.get(
            "last_seen"
        )

        was_offline = (
            old.get("online") is False
        )

        if isinstance(
            previous_seen,
            datetime
        ):

            elapsed = (
                now - previous_seen
            ).total_seconds()

            if elapsed > OFFLINE_THRESHOLD:
                was_offline = True

        device = {
            "ip": ip,
            "name": name,
            "user": user,
            "os": "Windows",
            "hw": hw,
            "latency": old.get(
                "latency",
                0
            ),
            "last_seen": now,
            "online": True,
            "agent_seen": True
        }

        devices[ip] = device

    save_device(
        ip,
        device
    )

    if was_offline:

        register_change(
            ip,
            name,
            "online"
        )

    # Busca comando pendente no banco
    job = deliver_command(ip)

    return jsonify({
        "ok": True,

        "command_id": (
            job["id"]
            if job
            else None
        ),

        "command": (
            job["command"]
            if job
            else None
        ),

        "message": (
            job["message"]
            if job
            else None
        )
    })


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
    ).strip()[:500]

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

        if not get_device_online(device):

            return jsonify({
                "ok": False,
                "error": "Agente indisponível"
            }), 409

    job_id = create_command(
        ip,
        command,
        message
    )

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

        conn.execute(
            "BEGIN IMMEDIATE"
        )

        row = conn.execute("""
            SELECT status, command
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

        previous, command = row

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

    if scan_lock.locked():

        return jsonify({
            "ok": False,
            "error": "Scan já em andamento"
        }), 409

    threading.Thread(
        target=scan_network,
        daemon=True
    ).start()

    audit(
        "scanner",
        "solicitado",
        "Escaneamento manual solicitado"
    )

    return jsonify({
        "ok": True,
        "status": "iniciado"
    }), 202


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
            description
        FROM audit_events
        WHERE 1=1
    """

    params = []

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
        "description"
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

from relatorios import registrar_relatorios

registrar_relatorios(
    app,
    require_admin,
    db_connect
)


# ==========================================
# INICIALIZAÇÃO
# ==========================================

if __name__ == "__main__":

    if not all((
        ADMIN_PASSWORD,
        AGENT_TOKEN,
        SECRET_KEY
    )):

        raise SystemExit(
            "Configure STI_ADMIN_PASSWORD, "
            "STI_AGENT_TOKEN e STI_SECRET_KEY."
        )

    init_db()

    load_devices()

    threading.Thread(
        target=scanner_loop,
        daemon=True
    ).start()

    logger.info(
        "STI Command Center V3 iniciado."
    )

    logger.info(
        "Rede monitorada: %s",
        NETWORK
    )

    app.run(
        host=HOST,
        port=PORT,
        debug=False,
        use_reloader=False
    )

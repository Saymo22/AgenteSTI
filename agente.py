
"""
============================================
STI COMMAND CENTER
AGENTE WINDOWS V3.2 - CLIENTE
============================================

Executável independente, sem arquivo BAT.

Funções:
- Conexão automática ao servidor STI
- Monitoramento de CPU, RAM e disco
- Nome do computador e usuário
- Uptime e impressoras
- Reconexão automática
- Recebimento de mensagens
- Confirmação de comandos
- Logs rotativos
- Instância única

Comandos de desligar/reiniciar:
DESATIVADOS POR PADRÃO; habilitação explícita por configuração externa
============================================
"""

import os
import sys
import time
import socket
import ctypes
import getpass
import logging
import platform
import threading
import sqlite3
from contextlib import contextmanager

from pathlib import Path
from urllib.parse import urlparse
from logging.handlers import RotatingFileHandler

import requests
import psutil
from configuracao import setting, positive_int


# ============================================
# 1 - CONFIGURAÇÕES DO SERVIDOR
# ============================================

VERSION = "3.2.0"

# IP do computador onde está o app.py
SERVER_IP = setting("STI_SERVER_IP", "10.2.116.121")

SERVER_PORT = positive_int("STI_SERVER_PORT", 5000, maximum=65535)

# IMPORTANTE:
# Configure o mesmo STI_AGENT_TOKEN do servidor no JSON ou ambiente.
# NÃO coloque a senha do administrador aqui.

AGENT_TOKEN = setting("STI_AGENT_TOKEN")

# Tempo entre envios
AGENT_INTERVAL = positive_int("AGENT_INTERVAL", 30)

# Tempo entre tentativas em caso de falha
RETRY_INTERVAL = positive_int("RETRY_INTERVAL", 10)

# Tempo máximo de conexão
CONNECT_TIMEOUT = 4
READ_TIMEOUT = 10

# Teste inicial em rede local.
# Para produção, configurar HTTPS.
USE_HTTPS = setting("STI_USE_HTTPS", "false").lower() == "true"

# Exige habilitação explícita para ações de energia.
ALLOW_POWER_COMMANDS = setting("STI_ALLOW_POWER_COMMANDS", "false").lower() == "true"

SCHEME = "https" if USE_HTTPS else "http"

SERVER_URL = (
    f"{SCHEME}://{SERVER_IP}:{SERVER_PORT}"
)

API_URL = SERVER_URL + "/api/agent"

STATUS_URL = (
    SERVER_URL + "/api/agent/command-status"
)

HTTP_TIMEOUT = (
    CONNECT_TIMEOUT,
    READ_TIMEOUT
)


# ============================================
# 2 - LOGS LOCAIS
# ============================================

APPDATA = Path(
    os.environ.get(
        "LOCALAPPDATA",
        str(Path.home())
    )
)

LOG_DIR = APPDATA / "STI" / "logs"

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True
)

LOG_FILE = (
    LOG_DIR / "agente_v3_1.log"
)

logger = logging.getLogger(
    "STI_AGENT"
)

logger.setLevel(
    logging.INFO
)

logger.propagate = False

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)

if not logger.handlers:

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )

    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    if sys.stdout is not None:

        console_handler = logging.StreamHandler(
            sys.stdout
        )

        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)


# ============================================
# 3 - CONTROLE DE INSTÂNCIA ÚNICA
# ============================================

mutex_handle = None


def verificar_instancia_unica():

    global mutex_handle

    kernel32 = ctypes.WinDLL(
        "kernel32",
        use_last_error=True
    )

    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_wchar_p
    ]

    kernel32.CreateMutexW.restype = (
        ctypes.c_void_p
    )

    mutex_handle = kernel32.CreateMutexW(
        None,
        False,
        "Local\\STI_Agente_V3_1"
    )

    if not mutex_handle:

        logger.error(
            "Não foi possível criar mutex."
        )

        return False

    if ctypes.get_last_error() == 183:

        logger.warning(
            "STI Agente já está em execução."
        )

        kernel32.CloseHandle(
            ctypes.c_void_p(mutex_handle)
        )

        mutex_handle = None

        return False

    return True


# ============================================
# 4 - VALIDAR CONFIGURAÇÕES
# ============================================

def validar_configuracoes():

    if platform.system() != "Windows":

        logger.error(
            "Este agente funciona somente no Windows."
        )

        return False

    if (
        not AGENT_TOKEN
        or AGENT_TOKEN == "COLE_AQUI_O_TOKEN_DO_AGENTE"
    ):

        logger.error(
            "Configure STI_AGENT_TOKEN no ambiente ou em sti-config.json."
        )

        return False

    parsed = urlparse(SERVER_URL)

    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
    ):

        logger.error(
            "Endereço do servidor inválido."
        )

        return False

    if not USE_HTTPS:

        logger.warning(
            "ATENÇÃO: conexão HTTP sem criptografia. "
            "Usar apenas em piloto controlado."
        )

    return True


# ============================================
# 5 - IDENTIFICAR COMPUTADOR
# ============================================

def obter_hostname():

    try:
        return socket.gethostname()

    except Exception:
        return "Windows"


def obter_usuario():

    try:

        try:
            import win32ts
            active = [item for item in win32ts.WTSEnumerateSessions()
                      if item["State"] == win32ts.WTSActive]
            if active:
                session_id = active[0]["SessionId"]
                user = win32ts.WTSQuerySessionInformation(None, session_id, win32ts.WTSUserName)
                domain = win32ts.WTSQuerySessionInformation(None, session_id, win32ts.WTSDomainName)
                if user:
                    return f"{domain}\\{user}" if domain else user
        except Exception:
            logger.debug("Sessão Windows indisponível; usando usuário do processo.", exc_info=True)
        user = getpass.getuser()

        domain = os.environ.get(
            "USERDOMAIN",
            ""
        )

        if domain:

            return f"{domain}\\{user}"

        return user

    except Exception:

        return "Desconhecido"


# ============================================
# 6 - IDENTIFICAR REDE
# ============================================

def obter_ip_local():

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    try:

        # A conexão UDP é usada para descobrir
        # a interface de saída. Não envia dados.
        sock.connect(
            (SERVER_IP, SERVER_PORT)
        )

        return sock.getsockname()[0]

    except OSError:

        return "Desconhecido"

    finally:

        sock.close()


def testar_porta_servidor():

    try:

        with socket.create_connection(
            (SERVER_IP, SERVER_PORT),
            timeout=CONNECT_TIMEOUT
        ):

            return True

    except OSError:

        return False


# ============================================
# 7 - IMPRESSORAS
# ============================================

def obter_impressoras():

    try:

        import win32print

        flags = (
            win32print.PRINTER_ENUM_LOCAL
            | win32print.PRINTER_ENUM_CONNECTIONS
        )

        printers = win32print.EnumPrinters(
            flags
        )

        return [
            str(item[2])[:250]
            for item in printers[:30]
            if len(item) > 2 and item[2]
        ]

    except ImportError:

        return []

    except Exception:

        logger.exception(
            "Erro ao consultar impressoras."
        )

        return []


# ============================================
# 8 - COLETAR HARDWARE
# ============================================

def coletar_hardware():

    cpu = psutil.cpu_percent(
        interval=0.3
    )

    memory = psutil.virtual_memory()

    drive = os.environ.get(
        "SystemDrive",
        "C:"
    ) + "\\"

    try:

        disk = psutil.disk_usage(
            drive
        )

    except OSError:

        logger.warning(
            "Não foi possível consultar o disco."
        )

        disk = None

    gb = 1024 ** 3

    uptime = max(
        0,
        int(
            time.time()
            - psutil.boot_time()
        )
    )

    return {
        "cpu": round(cpu, 1),

        "ram_total": round(
            memory.total / gb,
            2
        ),

        "ram_free": round(
            memory.available / gb,
            2
        ),

        "disk_total": (
            round(disk.total / gb, 2)
            if disk else None
        ),

        "disk_free": (
            round(disk.free / gb, 2)
            if disk else None
        ),

        "uptime": uptime,

        "printers": obter_impressoras()
    }


# ============================================
# 9 - MONTAR DADOS DO COMPUTADOR
# ============================================

def coletar_dados():

    hardware = coletar_hardware()

    return {
        "name": obter_hostname()[:120],

        "user": obter_usuario()[:120],

        "agent_version": VERSION,
        "capabilities": ["msg"] + (["restart", "shutdown"] if ALLOW_POWER_COMMANDS else []),
        "os": (
            platform.system()
            + " "
            + platform.release()
        ),

        **hardware
    }


# ============================================
# 10 - CONFIRMAR COMANDO NO SERVIDOR
# ============================================

def confirmar_comando(
    command_id,
    status,
    result=""
):

    payload = {
        "id": str(command_id),
        "status": str(status),
        "result": str(result)[:500]
    }

    try:

        response = requests.post(
            STATUS_URL,
            json=payload,
            headers={
                "X-Agent-Token": AGENT_TOKEN
            },
            timeout=HTTP_TIMEOUT
        )

        if response.status_code in (404, 409):
            raise CommandClosed("Servidor encerrou ou expirou o comando; não será reexecutado.")
        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict) or data.get("ok") is not True:

            logger.error(
                "Servidor recusou confirmação."
            )

            return False

        logger.info(
            "Comando %s confirmado: %s",
            command_id,
            status
        )

        return True

    except requests.RequestException:

        logger.exception(
            "Erro ao confirmar comando."
        )

        return False

    except ValueError:

        logger.error(
            "Resposta inválida ao confirmar comando."
        )

        return False


# ============================================
# 11 - MENSAGEM WINDOWS
# ============================================

def exibir_mensagem(message):

    try:

        logger.info(
            "Tentando exibir janela do STI."
        )

        # MB_OK | MB_ICONINFORMATION |
        # MB_TOPMOST | MB_SETFOREGROUND
        result = ctypes.windll.user32.MessageBoxW(
            0,
            str(message),
            "STI - Mensagem da Administração",
            0x00000040 | 0x00040000 | 0x00010000
        )

        if result == 1:

            return (
                "completed",
                "Janela exibida e fechada."
            )

        return (
            "failed",
            f"MessageBox retornou {result}"
        )

    except Exception as error:

        logger.exception(
            "Falha ao exibir mensagem."
        )

        return (
            "failed",
            str(error)
        )


# ============================================
# 12 - EXECUTAR COMANDOS
# ============================================

def agendar_energia(command):
    """Usa a API nativa sem fechar à força aplicativos com alterações pendentes."""
    import win32api
    import win32con
    import win32security

    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(), win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY
    )
    previous = None
    try:
        privilege = win32security.LookupPrivilegeValue(None, win32con.SE_SHUTDOWN_NAME)
        previous = win32security.AdjustTokenPrivileges(
            token, False, [(privilege, win32con.SE_PRIVILEGE_ENABLED)]
        )
        win32api.InitiateSystemShutdown(
            None, "STI: ação solicitada pela administração. Salve seu trabalho.",
            60, False, command == "restart"
        )
    finally:
        try:
            if previous is not None:
                win32security.AdjustTokenPrivileges(token, False, previous)
        finally:
            token.Close()


def executar_comando(
    command,
    message=""
):

    logger.info(
        "Executando solicitação: %s",
        command
    )

    # MENSAGEM
    if command == "msg":

        text = str(message).strip()

        if not text:

            return (
                "rejected",
                "Mensagem vazia."
            )

        if len(text) > 500:

            return (
                "rejected",
                "Mensagem muito longa."
            )

        return exibir_mensagem(text)

    # Nenhuma execução de shell livre; somente ações fixas e opt-in local.
    if command in ("restart", "shutdown"):
        if not ALLOW_POWER_COMMANDS:
            return "rejected", "Comandos de energia desativados neste agente."
        try:
            agendar_energia(command)
            return "initiated", "Ação de energia agendada para 60 segundos; não confirma sua conclusão."
        except Exception as error:
            return "failed", str(error)[:500]

    return (
        "rejected",
        "Comando não reconhecido."
    )


# ============================================
# 13 - PROCESSAMENTO EM THREAD
# ============================================

class CommandClosed(Exception):
    """O servidor não aceita mais confirmações para este job."""


JOURNAL_FILE = LOG_DIR.parent / "commands.db"
processed_commands = set()  # Somente threads ativas; histórico fica no SQLite.
processed_lock = threading.Lock()


@contextmanager
def journal_connect():
    conn = sqlite3.connect(str(JOURNAL_FILE), timeout=15)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_journal():
    with journal_connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, command TEXT NOT NULL, message TEXT NOT NULL,
            stage TEXT NOT NULL, status TEXT NOT NULL DEFAULT '',
            result TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL
        )""")
        # Um crash durante a ação tem resultado incerto: nunca repetir a ação.
        conn.execute("""UPDATE jobs SET stage='result', status='failed',
            result='Agente reiniciado durante execução; resultado incerto. Não reexecutado.',
            updated_at=? WHERE stage='running'""", (time.time(),))
        conn.execute("DELETE FROM jobs WHERE stage='acknowledged' AND updated_at < ?",
                     (time.time() - 7 * 86400,))


def update_job(command_id, stage, status="", result=""):
    with journal_connect() as conn:
        conn.execute("UPDATE jobs SET stage=?, status=?, result=?, updated_at=? WHERE id=?",
                     (stage, status, str(result)[:500], time.time(), command_id))


def executar_job(command_id, command, message):
    try:
        with journal_connect() as conn:
            row = conn.execute("SELECT stage, status, result FROM jobs WHERE id=?",
                               (command_id,)).fetchone()
        if not row or row[0] == "acknowledged":
            return
        stage, status, result = row
        if stage == "received":
            if not confirmar_comando(command_id, "accepted", "Recebido pelo agente STI."):
                return  # O próximo heartbeat tentará novamente, sem perder o job.
            update_job(command_id, "running")
            try:
                status, result = executar_comando(command, message)
            except Exception as error:
                logger.exception("Falha durante execução do comando.")
                status, result = "failed", str(error)
            update_job(command_id, "result", status, result)
        elif stage == "running":
            return
        if confirmar_comando(command_id, status, result):
            update_job(command_id, "acknowledged", status, result)
    except CommandClosed as error:
        logger.warning("Comando %s: %s", command_id, error)
        update_job(command_id, "acknowledged", status or "expired", result or str(error))
    except Exception:
        logger.exception("Falha ao processar comando; resultado mantido para nova tentativa.")
    finally:
        with processed_lock:
            processed_commands.discard(command_id)


def retry_pending_commands():
    with journal_connect() as conn:
        rows = conn.execute("SELECT id, command, message FROM jobs WHERE stage IN ('received', 'result')").fetchall()
    for command_id, command, message in rows:
        with processed_lock:
            if command_id in processed_commands:
                continue
            processed_commands.add(command_id)
        threading.Thread(target=executar_job, args=(command_id, command, message),
                         daemon=True, name="STI-Command").start()


def processar_comando(data):
    command_id, command = data.get("command_id"), data.get("command")
    if not command_id or not command:
        return
    if not isinstance(command_id, str) or len(command_id) > 64:
        logger.error("ID de comando inválido.")
        return
    if command not in ("msg", "restart", "shutdown"):
        logger.error("Comando desconhecido recebido.")
        return
    message = data.get("message") or ""
    if not isinstance(message, str) or len(message) > 500:
        logger.error("Mensagem inválida recebida.")
        return
    with journal_connect() as conn:
        conn.execute("""INSERT OR IGNORE INTO jobs
            (id, command, message, stage, updated_at) VALUES (?, ?, ?, 'received', ?)""",
            (command_id, command, message, time.time()))
    retry_pending_commands()


# ============================================
# 14 - COMUNICAR COM SERVIDOR
# ============================================

def comunicar_servidor(
    session_http,
    payload
):

    try:

        response = session_http.post(
            API_URL,
            json=payload,
            headers={
                "X-Agent-Token": AGENT_TOKEN
            },
            timeout=HTTP_TIMEOUT
        )

        if response.status_code == 401:

            logger.error(
                "Token de autenticação inválido."
            )

            return False

        if response.status_code == 403:

            logger.error(
                "IP não autorizado pelo servidor."
            )

            return False

        response.raise_for_status()

        data = response.json()

        if (
            not isinstance(data, dict)
            or data.get("ok") is not True
        ):

            logger.error(
                "Resposta inválida do servidor."
            )

            return False

        logger.info(
            "Dados enviados com sucesso."
        )

        processar_comando(data)

        return True

    except requests.exceptions.ConnectTimeout:

        logger.warning(
            "Tempo limite para conectar ao servidor."
        )

    except requests.exceptions.ConnectionError:

        logger.warning(
            "Servidor indisponível: %s",
            SERVER_URL
        )

    except requests.exceptions.ReadTimeout:

        logger.warning(
            "Servidor demorou para responder."
        )

    except requests.exceptions.HTTPError as error:

        logger.error(
            "Falha HTTP: %s",
            error
        )

    except ValueError:

        logger.exception(
            "Resposta JSON inválida."
        )

    except Exception:

        logger.exception(
            "Erro inesperado de comunicação."
        )

    return False


# ============================================
# 15 - DIAGNÓSTICO DA REDE
# ============================================

def diagnosticar_rede():

    logger.info(
        "Testando conexão com %s:%s",
        SERVER_IP,
        SERVER_PORT
    )

    logger.info(
        "IP local detectado: %s",
        obter_ip_local()
    )

    if testar_porta_servidor():

        logger.info(
            "Porta %s acessível no servidor.",
            SERVER_PORT
        )

        return True

    logger.warning(
        "Não foi possível acessar a porta %s "
        "no servidor %s.",
        SERVER_PORT,
        SERVER_IP
    )

    logger.warning(
        "Verifique o servidor, firewall "
        "e conectividade entre as redes."
    )

    return False


# ============================================
# 16 - INICIAR AGENTE
# ============================================

def iniciar_agente():

    logger.info("=" * 55)

    logger.info(
        "STI AGENTE WINDOWS V%s",
        VERSION
    )

    logger.info(
        "Servidor: %s",
        SERVER_URL
    )

    logger.info(
        "Máquina: %s",
        obter_hostname()
    )

    logger.info(
        "Usuário: %s",
        obter_usuario()
    )

    logger.info(
        "Intervalo: %s segundos",
        AGENT_INTERVAL
    )

    logger.info(
        "Comandos de energia: %s", "HABILITADOS" if ALLOW_POWER_COMMANDS else "BLOQUEADOS"
    )

    logger.info(
        "Arquivo de log: %s",
        LOG_FILE
    )

    logger.info("=" * 55)

    if not validar_configuracoes():
        return

    if not verificar_instancia_unica():
        return

    init_journal()
    diagnosticar_rede()

    with requests.Session() as session_http:

        while True:

            try:

                retry_pending_commands()
                payload = coletar_dados()

                sucesso = comunicar_servidor(
                    session_http,
                    payload
                )

                if sucesso:

                    time.sleep(
                        AGENT_INTERVAL
                    )

                else:

                    logger.info(
                        "Nova tentativa em %s segundos.",
                        RETRY_INTERVAL
                    )

                    time.sleep(
                        RETRY_INTERVAL
                    )

            except KeyboardInterrupt:

                logger.info(
                    "Agente encerrado."
                )

                break

            except Exception:

                logger.exception(
                    "Erro no ciclo principal."
                )

                time.sleep(
                    RETRY_INTERVAL
                )


# ============================================
# 17 - EXECUÇÃO
# ============================================

if __name__ == "__main__":

    try:

        if "--check" in sys.argv:
            import json
            if not validar_configuracoes():
                raise SystemExit(1)
            print(json.dumps(coletar_dados(), ensure_ascii=False, indent=2))
        else:
            iniciar_agente()

    except KeyboardInterrupt:

        logger.info(
            "Encerramento solicitado."
        )

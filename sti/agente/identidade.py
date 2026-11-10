"""Identidade persistente da instalação; MACs são referências, nunca a chave."""
import hashlib
import json
import logging
import os
import platform
import re
import socket
import sqlite3
import subprocess
import uuid
from functools import lru_cache
from pathlib import Path

import psutil
from sti.comum.configuracao import setting
from sti.comum.identidade import clean_serial

logger = logging.getLogger("STI_AGENT")
INSTANCE_ID = str(uuid.uuid4())


@lru_cache(maxsize=1)
def hardware_profile():
    profile = {"hardware_key": "", "key_kind": "", "serial_number": "", "manufacturer": "", "model": ""}
    if platform.system() != "Windows":
        return profile
    hardware_uuid = ""
    try:
        script = ("[Console]::OutputEncoding=[Text.UTF8Encoding]::new();"
                  "$p=Get-CimInstance Win32_ComputerSystemProduct -ErrorAction Stop;"
                  "$b=Get-CimInstance Win32_BIOS -ErrorAction Stop;"
                  "[pscustomobject]@{uuid=$p.UUID;serial=$b.SerialNumber;"
                  "manufacturer=$p.Vendor;model=$p.Name}|ConvertTo-Json -Compress")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, encoding="utf-8-sig", errors="replace", timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode == 0:
            data = json.loads(result.stdout)
            profile.update(serial_number=clean_serial(data.get("serial")),
                manufacturer=clean_serial(data.get("manufacturer")), model=clean_serial(data.get("model")))
            try:
                parsed = uuid.UUID(str(data.get("uuid", "")))
                if parsed.int not in (0, (1 << 128) - 1):
                    hardware_uuid = str(parsed)
            except ValueError:
                pass
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        logger.warning("Identificação SMBIOS indisponível; tentando identificação do Windows.")
    binding = "smbios:" + hardware_uuid if hardware_uuid else ""
    kind = "smbios" if hardware_uuid else ""
    if not binding:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                value = winreg.QueryValueEx(key, "MachineGuid")[0]
            binding = "windows:" + str(uuid.UUID(value))
            kind = "windows"
        except (OSError, ValueError, ImportError):
            logger.warning("Sem referência de hardware; a identificação usará apenas o UUID persistido.")
    if binding:
        profile["hardware_key"] = hashlib.sha256(binding.encode()).hexdigest()
        profile["key_kind"] = kind
    return profile


def mac_addresses():
    addresses = set()
    try:
        link_families = {psutil.AF_LINK, getattr(socket, "AF_PACKET", None)}
        for values in psutil.net_if_addrs().values():
            for item in values:
                mac = item.address.replace("-", ":").upper()
                if (item.family in link_families and re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", mac)
                        and mac != "00:00:00:00:00:00" and not int(mac[:2], 16) & 1):
                    addresses.add(mac)
    except (OSError, psutil.Error):
        logger.warning("Não foi possível consultar os MACs nesta coleta.")
    return sorted(addresses)[:32]


def identity_path():
    configured = setting("STI_IDENTITY_FILE", "")
    if configured:
        path = Path(configured).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    shared = Path(os.environ.get("PROGRAMDATA", str(Path.home()))) / "STI" / "identity.db"
    try:
        shared.parent.mkdir(parents=True, exist_ok=True)
        # Verifica o arquivo existente sem gerar uma nova identidade ao negar acesso.
        with shared.open("ab"):
            pass
        return shared
    except PermissionError:
        if shared.exists():
            # Outra conta pode ter criado o UUID: reutilizar leitura é melhor que duplicar o equipamento.
            with shared.open('rb'):
                pass
            return shared
        fallback = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "STI" / "identity.db"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        logger.warning("Sem acesso à identidade compartilhada. Usando %s; mantenha a mesma conta para executar o agente.", fallback)
        return fallback


def load_identity(path, hardware_key, key_kind=""):
    """Transação evita gerar dois UUIDs em inicializações simultâneas."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(path), timeout=15)
    except sqlite3.OperationalError:
        if path.is_file():
            return read_only_identity(path,hardware_key,key_kind)
        raise
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY CHECK(id=1), agent_id TEXT NOT NULL, hardware_key TEXT NOT NULL)")
            if 'key_kind' not in {r[1] for r in conn.execute('PRAGMA table_info(identity)')}:
                conn.execute("ALTER TABLE identity ADD COLUMN key_kind TEXT NOT NULL DEFAULT ''")
            row = conn.execute("SELECT agent_id, hardware_key, key_kind FROM identity WHERE id=1").fetchone()
            if row:
                agent_id = str(uuid.UUID(row[0]))  # Corrupção deve ser investigada, sem trocar UUID silenciosamente.
                if row[1] and hardware_key and row[1] != hardware_key:
                    if not key_kind or key_kind == row[2]:
                        agent_id = str(uuid.uuid4())
                        logger.warning("Referência de hardware mudou; nova identidade criada. Confira clonagem ou troca de placa-mãe.")
                    else:
                        # CIM indisponível pode mudar de SMBIOS para MachineGuid. Não é prova de clonagem.
                        hardware_key,key_kind = row[1],row[2]
                if not hardware_key:
                    hardware_key,key_kind = row[1],row[2]
            else:
                agent_id = str(uuid.uuid4())
            conn.execute("INSERT OR REPLACE INTO identity VALUES (1, ?, ?, ?)", (agent_id, hardware_key,key_kind))
        return agent_id
    except sqlite3.OperationalError as error:
        if 'readonly' not in str(error).lower() and 'read-only' not in str(error).lower():
            raise
        return read_only_identity(path,hardware_key,key_kind)
    finally:
        conn.close()


def read_only_identity(path, hardware_key, key_kind):
    conn = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=15)
    try:
        columns = {r[1] for r in conn.execute('PRAGMA table_info(identity)')}
        row = conn.execute('SELECT agent_id,hardware_key,' + ('key_kind' if 'key_kind' in columns else "''") + ' FROM identity WHERE id=1').fetchone()
        if not row:
            raise PermissionError('Identidade compartilhada vazia e sem permissão de gravação.')
        if row[1] and hardware_key and row[1] != hardware_key and key_kind == row[2]:
            raise PermissionError('Hardware diferente e identidade somente leitura; configure STI_IDENTITY_FILE com acesso de gravação.')
        logger.info('Reutilizando identidade compartilhada com acesso somente leitura.')
        return str(uuid.UUID(row[0]))
    finally:
        conn.close()


@lru_cache(maxsize=1)
def persistent_record():
    path = identity_path()
    profile = hardware_profile()
    agent_id = load_identity(path,profile['hardware_key'],profile['key_kind'])
    conn = sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=15)
    try:
        hardware_key = conn.execute('SELECT hardware_key FROM identity WHERE id=1').fetchone()[0]
    finally:
        conn.close()
    return {'agent_id':agent_id,'hardware_key':hardware_key}


def persistent_identity():
    return persistent_record()['agent_id']


def collect_identity():
    profile = {key:value for key,value in hardware_profile().items() if key != 'key_kind'}
    return {**profile, **persistent_record(), "instance_id": INSTANCE_ID, "mac_addresses": mac_addresses()}


def renew_identity():
    """Operação explícita de manutenção; execute com o agente parado."""
    path = identity_path()
    agent_id = str(uuid.uuid4())
    # Garante o esquema antes de substituir o UUID por solicitação do operador.
    profile = hardware_profile()
    load_identity(path, profile['hardware_key'],profile['key_kind'])
    conn = sqlite3.connect(str(path),timeout=15)
    try:
        with conn:
            conn.execute("UPDATE identity SET agent_id=? WHERE id=1",(agent_id,))
    finally:
        conn.close()
    persistent_record.cache_clear()
    logger.warning("Nova identidade criada por solicitação do operador: %s", agent_id)
    return agent_id

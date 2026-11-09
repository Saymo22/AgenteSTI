"""Integração com banco temporário; sem varredura nem ações reais nas máquinas."""
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".test-tmp"
WORK.mkdir(exist_ok=True)
os.environ.update({
    "STI_CONFIG_FILE": str(WORK / "no-config.json"),
    "STI_AGENT_TOKEN": "test-only-agent-token", "STI_ADMIN_PASSWORD": "test-only-admin",
    "STI_SECRET_KEY": "test-only-session-secret", "LOCALAPPDATA": str(WORK),
})

from sti.servidor import app as server
from sti.agente import cliente as agente
import requests
from scripts.preparar_config import preparar


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=WORK)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.db_patch = patch.object(server, "DB_FILE", self.folder / "server.db")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.journal_patch = patch.object(agente, "JOURNAL_FILE", self.folder / "agent.db")
        self.journal_patch.start()
        self.addCleanup(self.journal_patch.stop)
        server.devices.clear()
        server.login_attempts.clear()
        agente.processed_commands.clear()
        server.init_db()
        agente.init_journal()
        self.client = server.app.test_client()
        with self.client.session_transaction() as session:
            session["admin"] = True
        self.ip = "10.2.116.33"
        self.headers = {"X-Agent-Token": server.AGENT_TOKEN}
        self.payload = {
            "name": "PC-TESTE", "user": "TESTE\\usuario", "os": "Windows 11",
            "agent_version": "3.2.0", "capabilities": ["msg"], "cpu": 12.5,
            "ram_total": 16, "ram_free": 8, "disk_total": 256, "disk_free": 100,
            "uptime": 3600, "printers": ["Impressora de teste"],
        }

    def heartbeat(self, payload=None, ip=None):
        return self.client.post("/api/agent", json=self.payload if payload is None else payload,
                                headers=self.headers, environ_overrides={"REMOTE_ADDR": ip or self.ip})

    def command(self, command="msg", message="Mensagem de teste"):
        return self.client.post(f"/api/command/{self.ip}", json={"command": command, "message": message})

    def report(self, job_id, status, ip=None):
        return self.client.post("/api/agent/command-status", headers=self.headers,
            json={"id": job_id, "status": status, "result": "teste"},
            environ_overrides={"REMOTE_ADDR": ip or self.ip})

    def test_network_preserved_and_source_enforced(self):
        self.assertEqual(str(server.NETWORK), "10.2.116.0/22")
        for ip in ("10.2.116.33", "10.2.117.10", "10.2.118.10", "10.2.119.10"):
            self.assertEqual(self.heartbeat(ip=ip).status_code, 200)
        self.assertEqual(self.heartbeat(ip="10.2.120.10").status_code, 403)

    def test_auth_required(self):
        self.assertEqual(self.client.post("/api/agent", json=self.payload).status_code, 401)
        anonymous = server.app.test_client()
        for route in ("/api/devices", "/api/events", "/api/history", "/relatorios", "/api/report/events.csv"):
            self.assertEqual(anonymous.get(route).status_code, 401)

    def organization(self, changes, ip=None, client=None):
        return (client or self.client).patch(f"/api/devices/{ip or self.ip}/organization", json=changes)

    def test_organization_default_and_authenticated_edit(self):
        self.heartbeat()
        item = self.client.get('/api/devices').json['devices'][0]
        self.assertEqual(item['organization']['department'], '')
        anonymous = server.app.test_client()
        self.assertEqual(self.organization({'room': '101'}, client=anonymous).status_code, 401)
        response = self.client.patch(f'/api/devices/{self.ip}/organization', json={'room':'101'}, headers={'Origin':'https://outro.example'})
        self.assertEqual(response.status_code, 403)
        response = self.organization({'department':'Financeiro', 'room':'Sala 101', 'responsible':'Maria Silva'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['organization']['responsible'], 'Maria Silva')
        self.assertTrue(response.json['organization']['updated_at'])

    def test_organization_survives_agent_scanner_and_restart(self):
        self.heartbeat()
        self.organization({'department':'TI', 'room':'204', 'responsible':'João'})
        self.heartbeat({**self.payload, 'organization':{'department':'Indevido'}})
        import ipaddress
        with patch.object(server, 'NETWORK', ipaddress.ip_network('10.2.116.32/30')), patch.object(server, 'ping_host', return_value=(True, 1)):
            server.scan_network()
        server.devices.clear()
        server.load_devices()
        devices = self.client.get('/api/devices').json['devices']
        item = next(device for device in devices if device['ip'] == self.ip)
        self.assertEqual(item['organization']['department'], 'TI')
        self.assertEqual(item['organization']['room'], '204')
        self.assertEqual(item['organization']['responsible'], 'João')
        self.assertEqual(item['hw']['cpu'], 12.5)

    def test_organization_partial_clear_and_no_duplicate_audit(self):
        self.heartbeat()
        self.organization({'department':'  Financeiro  ', 'room':'204', 'responsible':'Maria'})
        response = self.organization({'room':''})
        self.assertEqual(response.json['organization']['department'], 'Financeiro')
        self.assertEqual(response.json['organization']['room'], '')
        self.assertEqual(response.json['organization']['responsible'], 'Maria')
        revision = response.json['organization']['updated_at']
        response = self.organization({'room':''})
        self.assertEqual(response.json['organization']['updated_at'], revision)
        events = self.client.get('/api/events?category=inventario').json['events']
        self.assertEqual(len(events), 2)
        self.assertEqual(self.client.get('/relatorios?category=inventario').status_code, 200)

    def test_organization_edit_offline_and_conflicting_revision(self):
        self.heartbeat()
        server.devices[self.ip]['last_seen'] -= timedelta(days=1)
        first = self.organization({'department':'TI', 'expected_updated_at':''})
        self.assertEqual(first.status_code, 200)
        revision = first.json['organization']['updated_at']
        self.assertEqual(self.organization({'department':'Outro', 'expected_updated_at':''}).status_code, 409)
        response = self.organization({'room':'303', 'expected_updated_at':revision})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['organization']['department'], 'TI')

    def test_organization_concurrent_saves_do_not_overwrite_each_other(self):
        self.heartbeat()
        def save(department):
            client = server.app.test_client()
            with client.session_transaction() as session:
                session['admin'] = True
            return self.organization({'department':department, 'expected_updated_at':''}, client=client).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(save, ['Financeiro', 'TI']))
        self.assertEqual(sorted(statuses), [200, 409])

    def test_organization_validation_and_known_devices(self):
        self.heartbeat()
        for payload in ({}, [], {'room':None}, {'room':True}, {'room':[]}, {'room':42}, {'room':'a'*121},
                        {'room':'A\x00B'}, {'ip':'10.2.117.1'}, {'room':'1', 'admin':True}, {'room':'1','expected_updated_at':42}):
            self.assertEqual(self.organization(payload).status_code, 400, payload)
        self.assertEqual(self.organization({'room':'1'}, ip='10.2.120.1').status_code, 400)
        self.assertEqual(self.organization({'room':'1'}, ip='10.2.116.99').status_code, 404)

    def test_organization_schema_migrates_old_database_without_touching_inventory(self):
        old_path = self.folder / 'before-organization.db'
        with closing(sqlite3.connect(old_path)) as conn, conn:
            conn.execute('CREATE TABLE device_state (ip TEXT PRIMARY KEY, name TEXT, user TEXT, os TEXT, hw TEXT, last_seen TEXT)')
            conn.execute('INSERT INTO device_state VALUES (?, ?, ?, ?, ?, ?)',
                         (self.ip, 'Legado', 'usuario', 'Windows', '{}', datetime.now().isoformat()))
        with patch.object(server, 'DB_FILE', old_path):
            server.init_db()
            server.init_db()
            server.devices.clear()
            server.load_devices()
            item = self.client.get('/api/devices').json['devices'][0]
            self.assertEqual(item['name'], 'Legado')
            self.assertEqual(item['organization']['department'], '')
            self.assertEqual(self.organization({'department':'Setor legado'}).status_code, 200)

    def test_panel_loads_local_scripts_and_agent_fields(self):
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('src="/static/painel.js"', page)
        self.assertIn('src="/static/vendor/chart.umd.min.js"', page)
        self.assertIn('href="/static/painel.css"', page)
        self.assertIn('id="modalAgentField"', page)
        self.assertIn('id="modalPrintersField"', page)
        self.assertNotIn('<script>', page)
        for path in ("/static/painel.js", "/static/painel.css", "/static/vendor/chart.umd.min.js"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            response.close()

    def test_telemetry_persists_os_metrics_and_capabilities(self):
        self.assertEqual(self.heartbeat().status_code, 200)
        item = self.client.get("/api/devices").json["devices"][0]
        self.assertEqual(item["os"], "Windows 11")
        self.assertEqual(item["hw"]["cpu"], 12.5)
        self.assertEqual(item["hw"]["printers"], self.payload["printers"])
        self.assertTrue(item["agent_online"])
        with server.db_connect() as conn:
            row = conn.execute("SELECT os, agent_version, last_agent_seen FROM device_state").fetchone()
        self.assertEqual(row[:2], ("Windows 11", "3.2.0"))
        self.assertIsNotNone(row[2])

    def test_invalid_metrics_rejected_without_overwriting(self):
        self.heartbeat()
        for field, value in (("cpu", 101), ("cpu", True), ("cpu", "abc"), ("ram_free", 100),
                             ("disk_free", -1), ("printers", "texto"), ("os", []), ("capabilities", ["shell"])):
            payload = {**self.payload, field: value}
            self.assertEqual(self.heartbeat(payload).status_code, 400, (field, value))
        self.assertEqual(server.devices[self.ip]["hw"]["cpu"], 12.5)

    def test_unknown_disk_is_not_zero(self):
        self.assertEqual(self.heartbeat({**self.payload, "disk_free": None, "disk_total": None}).status_code, 200)
        self.assertIsNone(self.client.get("/api/devices").json["devices"][0]["hw"]["disk_total"])

    def test_ping_does_not_keep_agent_available(self):
        self.heartbeat()
        device = server.devices[self.ip]
        device["last_agent_seen"] = datetime.now() - timedelta(seconds=server.OFFLINE_THRESHOLD + 1)
        device["last_seen"] = datetime.now()
        self.assertTrue(server.get_device_online(device))
        self.assertFalse(server.get_agent_online(device))
        self.assertEqual(self.command().status_code, 409)

    def test_scanner_preserves_telemetry_and_does_not_refresh_agent(self):
        import ipaddress
        self.heartbeat()
        last = server.devices[self.ip]["last_agent_seen"]
        with patch.object(server, "NETWORK", ipaddress.ip_network("10.2.116.32/30")), patch.object(server, "ping_host", side_effect=lambda ip: (ip == self.ip, 2.0)):
            self.assertTrue(server.scan_network())
        device = server.devices[self.ip]
        self.assertEqual(device["last_agent_seen"], last)
        self.assertEqual(device["hw"]["cpu"], 12.5)
        self.assertEqual(device["os"], "Windows 11")

    def test_accepted_job_expiration_and_snapshot_ordering(self):
        self.heartbeat()
        original = dict(server.devices[self.ip])
        job_id = self.command().json["command_id"]
        self.heartbeat()
        self.report(job_id, "accepted")
        with server.db_connect() as conn:
            conn.execute("UPDATE command_jobs SET updated_at=? WHERE id=?",
                         ((datetime.now() - timedelta(seconds=server.COMMAND_RUNNING_TTL + 1)).isoformat(), job_id))
        self.assertEqual(server.get_command(job_id)["status"], "expired")
        original["last_seen"] -= timedelta(days=1)
        original["hw"] = {"cpu": 99}
        server.save_device(self.ip, original)
        with server.db_connect() as conn:
            hw = json.loads(conn.execute("SELECT hw FROM device_state WHERE ip=?", (self.ip,)).fetchone()[0])
        self.assertEqual(hw["cpu"], 12.5)

    def test_unicode_password_and_non_ascii_invalid_token(self):
        with patch.object(server, "ADMIN_PASSWORD", "Senha-com-acentuação"):
            self.assertEqual(self.client.post("/login", data={"password": "Senha-com-acentuação"}).status_code, 302)
        self.assertEqual(self.client.post("/api/agent", json=self.payload, headers={"X-Agent-Token": "inválido"}).status_code, 401)

    def test_power_capability_enforced(self):
        self.heartbeat()
        self.assertEqual(self.command("restart").status_code, 409)
        self.heartbeat({**self.payload, "capabilities": ["msg", "restart", "shutdown"]})
        self.assertEqual(self.command("restart").status_code, 202)

    def test_full_command_lifecycle_and_ownership(self):
        self.heartbeat()
        response = self.command()
        self.assertEqual(response.status_code, 202)
        job_id = response.json["command_id"]
        self.assertEqual(self.heartbeat().json["command_id"], job_id)
        self.assertEqual(self.report(job_id, "accepted", "10.2.117.10").status_code, 404)
        self.assertEqual(self.report(job_id, "completed").status_code, 409)
        self.assertEqual(self.report(job_id, "accepted").status_code, 200)
        self.assertEqual(self.report(job_id, "accepted").status_code, 200)
        self.assertEqual(self.report(job_id, "completed").status_code, 200)
        self.assertEqual(self.report(job_id, "completed").status_code, 200)
        self.assertEqual(self.client.get(f"/api/commands/{job_id}").json["job"]["status"], "completed")
        self.assertEqual(self.command().status_code, 202)

    def test_lost_delivery_is_redelivered_until_accepted(self):
        self.heartbeat()
        job_id = self.command().json["command_id"]
        for _ in range(3):
            self.assertEqual(self.heartbeat().json["command_id"], job_id)
        self.report(job_id, "accepted")
        self.assertIsNone(self.heartbeat().json["command_id"])

    def test_expiration_unblocks_next_command_without_reexecution(self):
        self.heartbeat()
        job_id = self.command().json["command_id"]
        self.heartbeat()
        with server.db_connect() as conn:
            conn.execute("UPDATE command_jobs SET requested_at=? WHERE id=?",
                         ((datetime.now() - timedelta(seconds=server.COMMAND_TTL + 1)).isoformat(), job_id))
        self.assertEqual(self.client.get(f"/api/commands/{job_id}").json["job"]["status"], "expired")
        self.assertEqual(self.report(job_id, "accepted").status_code, 409)
        self.assertEqual(self.command().status_code, 202)

    def test_concurrent_commands_only_one_is_created(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: server.create_command(self.ip, "msg", "teste"), range(8)))
        self.assertEqual(sum(item is not None for item in results), 1)

    def test_login_rate_limit_and_origin_guard(self):
        client = server.app.test_client()
        for _ in range(5):
            self.assertEqual(client.post("/login", data={"password": "errada"}).status_code, 401)
        self.assertEqual(client.post("/login", data={"password": "errada"}).status_code, 429)
        self.assertEqual(self.client.post("/api/scan", headers={"Origin": "https://outro.example"}).status_code, 403)

    def test_report_date_range_csv_and_validation(self):
        server.audit("dispositivo", "online", "=FORMULA()", self.ip, "=TESTE()")
        today = datetime.now().strftime("%Y-%m-%d")
        csv = self.client.get(f"/api/report/events.csv?start={today}&end={today}")
        self.assertEqual(csv.status_code, 200)
        self.assertIn("'=FORMULA()", csv.get_data(as_text=True))
        self.assertEqual(self.client.get("/relatorios?start=invalida").status_code, 400)
        self.assertEqual(self.client.get("/relatorios?start=2026-11-05&end=2026-11-01").status_code, 400)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_existing_database_migration_and_restart_require_new_heartbeat(self):
        self.heartbeat()
        server.devices.clear()
        server.init_db()
        server.load_devices()
        self.assertEqual(server.devices[self.ip]["os"], "Windows 11")
        self.assertFalse(server.get_agent_online(server.devices[self.ip]))
        # Real old schema, not only an already-migrated database.
        old_path = self.folder / "old.db"
        with closing(sqlite3.connect(old_path)) as conn, conn:
            conn.execute("CREATE TABLE device_state (ip TEXT PRIMARY KEY, name TEXT, user TEXT, os TEXT, hw TEXT, last_seen TEXT)")
        with patch.object(server, "DB_FILE", old_path):
            server.init_db()
            with server.db_connect() as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(device_state)")}
            self.assertIn("last_agent_seen", columns)

    def store_local_job(self, job_id):
        with patch.object(agente, "retry_pending_commands"):
            agente.processar_comando({"command_id": job_id, "command": "msg", "message": "teste"})

    def test_agent_retries_acceptance_and_final_result_without_repeating_action(self):
        self.store_local_job("job-test")
        with patch.object(agente, "confirmar_comando", return_value=False), patch.object(agente, "executar_comando") as execute:
            agente.executar_job("job-test", "msg", "teste")
            execute.assert_not_called()
        with patch.object(agente, "confirmar_comando", side_effect=[True, False]), patch.object(agente, "executar_comando", return_value=("completed", "OK")) as execute:
            agente.executar_job("job-test", "msg", "teste")
            execute.assert_called_once()
        with patch.object(agente, "confirmar_comando", return_value=True), patch.object(agente, "executar_comando") as execute:
            agente.executar_job("job-test", "msg", "teste")
            agente.executar_job("job-test", "msg", "teste")
            execute.assert_not_called()

    def test_agent_restart_during_execution_does_not_repeat_action(self):
        self.store_local_job("crash-test")
        agente.update_job("crash-test", "running")
        agente.init_journal()
        with patch.object(agente, "confirmar_comando", return_value=True) as confirm, patch.object(agente, "executar_comando") as execute:
            agente.executar_job("crash-test", "msg", "teste")
            execute.assert_not_called()
            self.assertEqual(confirm.call_args.args[1], "failed")

    def test_agent_server_roundtrip_using_real_http_payloads(self):
        self.heartbeat()
        job_id = self.command().json["command_id"]
        self.heartbeat()
        self.store_local_job(job_id)
        def post(url, json, headers, timeout):
            reply = self.client.post("/api/agent/command-status", json=json, headers=headers,
                                     environ_overrides={"REMOTE_ADDR": self.ip})
            response = requests.Response()
            response.status_code = reply.status_code
            response._content = reply.data
            return response
        with patch.object(agente.requests, "post", side_effect=post), patch.object(agente, "executar_comando", return_value=("completed", "Fechada")):
            agente.executar_job(job_id, "msg", "teste")
        self.assertEqual(server.get_command(job_id)["status"], "completed")

    def test_power_command_is_opt_in_and_never_uses_shell(self):
        with patch.object(agente, "ALLOW_POWER_COMMANDS", False), patch.object(agente, "agendar_energia") as run:
            self.assertEqual(agente.executar_comando("shutdown")[0], "rejected")
            run.assert_not_called()
        with patch.object(agente, "ALLOW_POWER_COMMANDS", True), patch.object(agente, "agendar_energia") as run:
            self.assertEqual(agente.executar_comando("restart")[0], "initiated")
            run.assert_called_once_with("restart")

    def test_native_power_api_does_not_force_close_applications(self):
        from unittest.mock import MagicMock
        api, security, constants = MagicMock(), MagicMock(), MagicMock()
        with patch.dict("sys.modules", {"win32api": api, "win32security": security, "win32con": constants}):
            agente.agendar_energia("restart")
        self.assertEqual(api.InitiateSystemShutdown.call_args.args[2:], (60, False, True))
        self.assertEqual(security.AdjustTokenPrivileges.call_count, 2)
        security.OpenProcessToken.return_value.Close.assert_called_once()

    def test_provisioning_keeps_admin_secret_out_of_agent_config(self):
        preparar(self.folder)
        server_config = json.loads((self.folder / "sti-config.json").read_text(encoding="utf-8"))
        agent_config = json.loads((self.folder / "agent-config.json").read_text(encoding="utf-8"))
        self.assertEqual(agent_config["STI_AGENT_TOKEN"], server_config["STI_AGENT_TOKEN"])
        self.assertNotIn("STI_ADMIN_PASSWORD", agent_config)
        self.assertNotIn("STI_SECRET_KEY", agent_config)
        with self.assertRaises(SystemExit):
            preparar(self.folder)


if __name__ == "__main__":
    unittest.main()

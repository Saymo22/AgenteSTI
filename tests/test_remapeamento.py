"""Remapeamento com rede simulada e banco temporário."""
import ipaddress
import sqlite3
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch
from types import SimpleNamespace

import test_integracao as fixtures
from sti.servidor import app as server


class ImmediateThread:
    def __init__(self, target, kwargs=None, **options):
        self.target = target
        self.kwargs = kwargs or {}

    def start(self):
        self.target(**self.kwargs)


class RemapTests(unittest.TestCase):
    def setUp(self):
        fixtures.IntegrationTests.setUp(self)
        server.scan_status.update(scanning=False, remapping=False, discovery_generation=0, last_remap=None, error=None)

    def discover(self, ip, online=False):
        device = {'ip': ip, 'name': 'nome-antigo.local', 'name_source': 'dns', 'user': 'Não informado',
                  'os': 'Desconhecido', 'hw': {}, 'last_seen': datetime.now() - timedelta(seconds=0 if online else 3600),
                  'online': online, 'agent_seen': False, 'latency': 3 if online else None}
        server.devices[ip] = device
        server.save_device(ip, device)
        return device

    def heartbeat(self, ip=None, **extra):
        return fixtures.IntegrationTests.heartbeat(self, {**self.payload, **extra}, ip)

    def remap(self, ping_ip='10.2.116.34'):
        with patch.object(server, 'threading', SimpleNamespace(Thread=ImmediateThread)), patch.object(server, 'NETWORK', ipaddress.ip_network('10.2.116.32/30')), patch.object(server, 'ping_host', side_effect=lambda ip: (ip == ping_ip, 3)):
            return self.client.post('/api/remap', json={'confirm': True})

    def test_preview_counts_discovery_and_preserves_legacy_and_permanent_agents(self):
        self.discover('10.2.117.50')
        self.discover('10.2.118.51', online=True)
        self.heartbeat()
        agent = {'agent_id': str(uuid.uuid4()), 'instance_id': str(uuid.uuid4()), 'hardware_key': 'a' * 64}
        self.heartbeat('10.2.119.52', **agent)
        self.heartbeat('10.2.119.52', **{**agent, 'agent_id': str(uuid.uuid4()), 'hardware_key': 'b' * 64})
        preview = self.client.get('/api/remap').json
        self.assertEqual(preview['removed'], 2)
        self.assertEqual(preview['online_removed'], 1)
        self.assertEqual(preview['offline_removed'], 1)
        self.assertEqual(preview['kept'], 3)  # Inclui o cadastro permanente sem vínculo de IP atual.
        self.assertEqual(preview['network'], '10.2.116.0/22')
        server.devices.clear()
        server.load_devices()
        self.assertEqual(self.client.get('/api/remap').json['removed'], 2)

    def test_remap_removes_old_discovery_rediscovers_active_and_preserves_metadata_history(self):
        self.heartbeat()
        self.discover('10.2.117.50')
        self.discover('10.2.116.34')
        self.client.patch('/api/devices/10.2.116.34/organization', json={'room': 'Sala 12'})
        server.audit('dispositivo', 'offline', 'Histórico anterior', ip='10.2.117.50')
        job = server.create_command('10.2.117.50', 'msg', 'Antigo')
        reply = self.remap()
        self.assertEqual(reply.status_code, 202, reply.json)
        self.assertEqual(reply.json['scan']['last_remap']['removed'], 2)
        self.assertEqual(reply.json['scan']['last_remap']['status'], 'completed')
        self.assertFalse(server.scan_lock.locked())
        items = self.client.get('/api/devices').json['devices']
        self.assertEqual({d['ip'] for d in items}, {self.ip, '10.2.116.34'})
        rediscovered = next(d for d in items if d['ip'] == '10.2.116.34')
        self.assertEqual(rediscovered['name'], '10.2.116.34')
        self.assertEqual(rediscovered['organization']['room'], 'Sala 12')
        self.assertEqual(server.get_command(job)['status'], 'expired')
        self.assertTrue(any(e['description'] == 'Histórico anterior' for e in self.client.get('/api/events').json['events']))
        server.devices.clear()
        server.load_devices()
        self.assertNotIn('10.2.117.50', server.devices)
        self.assertIn(self.ip, server.devices)

    def test_agent_identified_after_preview_is_kept(self):
        self.discover('10.2.116.34')
        self.assertEqual(self.client.get('/api/remap').json['removed'], 1)
        self.heartbeat('10.2.116.34')
        reply = self.remap()
        self.assertEqual(reply.json['scan']['last_remap']['removed'], 0)
        self.assertEqual(server.devices['10.2.116.34']['name'], self.payload['name'])

    def test_auth_confirmation_origin_and_busy_scan_do_not_remove_anything(self):
        self.discover('10.2.117.50')
        anonymous = server.app.test_client()
        self.assertEqual(anonymous.get('/api/remap').status_code, 401)
        self.assertEqual(anonymous.post('/api/remap', json={'confirm': True}).status_code, 401)
        for data in ({}, {'confirm': False}, {'confirm': 'true'}, []):
            self.assertEqual(self.client.post('/api/remap', json=data).status_code, 400)
        self.assertEqual(self.client.post('/api/remap', json={'confirm': True}, headers={'Origin': 'https://outro.example'}).status_code, 403)
        server.scan_lock.acquire()
        try:
            self.assertEqual(self.client.post('/api/remap', json={'confirm': True}).status_code, 409)
            self.assertEqual(self.client.post('/api/scan').status_code, 409)
        finally:
            server.scan_lock.release()
        self.assertIn('10.2.117.50', server.devices)

    def test_failed_thread_start_keeps_records_and_releases_scan_lock(self):
        self.discover('10.2.117.50')
        with patch.object(server.threading, 'Thread') as thread, self.assertLogs('STI', level='ERROR'):
            thread.return_value.start.side_effect = RuntimeError('Não iniciou')
            self.assertEqual(self.client.post('/api/remap', json={'confirm': True}).status_code, 503)
        self.assertFalse(server.scan_lock.locked())
        self.assertIn('10.2.117.50', server.devices)
        self.assertEqual(self.remap().status_code, 202)

    def test_failed_cleanup_rolls_back_database_before_changing_memory(self):
        self.discover('10.2.117.50')
        self.discover('10.2.118.51')
        original_connect = server.db_connect

        class FailingConnection:
            def __init__(self, conn):
                self.conn = conn
                self.deletes = 0

            def execute(self, query, parameters=()):
                if query.startswith('DELETE FROM device_state'):
                    self.deletes += 1
                    if self.deletes == 2:
                        raise sqlite3.OperationalError('Falha simulada')
                return self.conn.execute(query, parameters)

        @contextmanager
        def failing_connect():
            with original_connect() as conn:
                yield FailingConnection(conn)

        with patch.object(server, 'db_connect', failing_connect), self.assertRaises(sqlite3.OperationalError):
            server.clear_discovery_devices()
        self.assertEqual(len(server.devices), 2)
        with server.db_connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM device_state').fetchone()[0], 2)

    def test_late_dns_snapshot_does_not_recreate_removed_device(self):
        snapshot = dict(self.discover('10.2.117.50'))
        self.assertEqual(server.clear_discovery_devices(), 1)
        server.save_device(snapshot['ip'], snapshot)
        with server.db_connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM device_state').fetchone()[0], 0)
        self.assertNotIn(snapshot['ip'], server.devices)

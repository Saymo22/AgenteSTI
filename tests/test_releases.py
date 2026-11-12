"""Releases, assinatura e recuperação em diretórios temporários, sem registrar o Windows."""
import io
import json
import os
import uuid
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, Mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import test_integracao as fixtures
from sti.comum import releases as protocol
from sti.agente import atualizacao
from sti.servidor import app as server
from sti.servidor import releases
from scripts.gerar_release import create_bundle


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        fixtures.IntegrationTests.setUp(self)
        key = Ed25519PrivateKey.generate()
        self.key_file = self.folder / 'private.pem'
        self.key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        public = self.folder / 'public.pem'
        public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        key_patch = patch.object(protocol, 'PUBLIC_KEY_FILE', public)
        key_patch.start()
        self.addCleanup(key_patch.stop)
        self.payload.update(agent_id=str(uuid.uuid4()), instance_id=str(uuid.uuid4()), hardware_key='a'*64,
                            agent_version='3.4.0', update_supported=True, update_protocol=1)
        self.root = self.folder / 'STI' / 'Agent'
        self.config = {'STI_SERVER_IP': '10.2.116.121', 'STI_SERVER_PORT': 5000, 'STI_AGENT_TOKEN': 'local-test-token'}

    def bundle(self, version='3.4.1', content=b'MZ-new-agent', msi=False):
        source = self.folder / ('source-' + version)
        source.mkdir(exist_ok=True)
        agent, installer = source / 'agent.exe', source / ('setup.msi' if msi else 'setup.exe')
        agent.write_bytes(content)
        installer.write_bytes(b'MZ-fixture-installer')
        artifacts = create_bundle(agent, installer, version, 'Notas de teste', self.key_file, source / 'out')
        return artifacts[0], json.loads(artifacts[2].read_text(encoding='utf-8'))

    def publish(self, version='3.4.1'):
        bundle, envelope = self.bundle(version)
        response = self.client.post('/api/releases', data={'release': (io.BytesIO(bundle.read_bytes()), 'release.sti')})
        self.assertEqual(response.status_code, 201, response.json)
        return envelope

    def heartbeat(self, **extra):
        return fixtures.IntegrationTests.heartbeat(self, {**self.payload, **extra})


    def test_signed_publication_policy_heartbeat_download_and_pause(self):
        envelope = self.publish()
        heartbeat = self.heartbeat()
        device_id = heartbeat.json['device_id']
        self.assertIsNone(heartbeat.json['update'])
        reply = self.client.post('/api/releases/activate', json={'version': '3.4.1', 'scope': 'selected', 'device_ids': [device_id]})
        self.assertEqual(reply.status_code, 200)
        offered = self.heartbeat().json['update']
        self.assertEqual(offered['release'], envelope)
        conflict = self.client.post('/api/releases/activate', json={'version': '3.4.1', 'expected_rollout_id': ''})
        self.assertEqual(conflict.status_code, 409)
        progress = {'agent_id': self.payload['agent_id'], 'agent_version': '3.4.0',
                    'update_supported': True, 'update_status': {'status': 'downloading', 'target_version': '3.4.1'}}
        reported = self.client.post('/api/agent/update-status', json=progress, headers=self.headers,
                                   environ_overrides={'REMOTE_ADDR': self.ip})
        self.assertEqual(reported.status_code, 200)
        self.assertEqual(self.client.get('/api/releases').json['devices'][0]['status'], 'downloading')
        refused = self.client.post('/api/agent/update-status', json=progress, headers=self.headers,
                                  environ_overrides={'REMOTE_ADDR': '10.2.117.99'})
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(self.heartbeat(update_supported=False).json['update'], None)
        headers = {**self.headers, 'X-Agent-ID': self.payload['agent_id']}
        response = self.client.get('/api/agent/releases/3.4.1/package', headers=headers, environ_overrides={'REMOTE_ADDR': self.ip})
        self.assertEqual(response.status_code, 200)
        response.close()
        wrong = self.client.get('/api/agent/releases/3.4.1/package', headers=headers, environ_overrides={'REMOTE_ADDR': '10.2.117.99'})
        self.assertEqual(wrong.status_code, 403)
        self.client.post('/api/releases/pause')
        self.assertIsNone(self.heartbeat().json['update'])

    def test_tampered_package_bad_signature_and_unsigned_upload_are_rejected(self):
        bundle, envelope = self.bundle()
        envelope['manifest']['version'] = '3.5.0'
        with self.assertRaises(ValueError):
            protocol.verify_manifest(envelope)
        raw = io.BytesIO()
        with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(raw, 'w') as target:
            for name in source.namelist():
                target.writestr(name, b'altered' if name == 'agent.zip' else source.read(name))
        response = self.client.post('/api/releases', data={'release': (io.BytesIO(raw.getvalue()), 'bad.sti')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/releases').json['releases'], [])
        self.assertEqual(self.client.post('/api/releases', data={'release': (io.BytesIO(b'invalid'), 'bad.sti')}).status_code, 400)

    def test_published_versions_are_immutable_and_upload_does_not_expand_telemetry_limit(self):
        self.publish()
        bundle, _ = self.bundle(content=b'MZ-different-agent')
        self.assertEqual(self.client.post('/api/releases', data={'release': (io.BytesIO(bundle.read_bytes()), 'another.sti')}).status_code, 400)
        huge = {**self.payload, 'extra': 'x'*40000}
        self.assertEqual(fixtures.IntegrationTests.heartbeat(self, huge).status_code, 413)

    def test_auth_origin_and_policy_validation(self):
        anonymous = server.app.test_client()
        self.assertEqual(anonymous.get('/api/releases').status_code, 401)
        self.assertEqual(anonymous.post('/api/releases/activate', json={}).status_code, 401)
        self.assertEqual(self.client.post('/api/releases/pause', headers={'Origin': 'https://other.example'}).status_code, 403)
        self.publish()
        self.assertEqual(self.client.post('/api/releases/activate', json={'version': '3.4.1', 'scope': 'selected'}).status_code, 400)
        self.assertEqual(self.client.post('/api/releases/activate', json={'version': '3.4.1', 'window_start': '23:00'}).status_code, 400)
        self.assertEqual(self.client.post('/api/releases/activate', json={'version': '99.0.0'}).status_code, 404)

    def test_windows_cross_midnight_and_version_order(self):
        self.assertTrue(releases.in_window('22:00','06:00',datetime(2026,11,11,23,0)))
        self.assertFalse(releases.in_window('22:00','06:00',datetime(2026,11,11,12,0)))
        self.assertTrue(releases.in_window('22:00','06:00',datetime(2026,11,11,5,59)))
        self.assertGreater(protocol.version_tuple('3.10.0'),protocol.version_tuple('3.9.0'))
        self.publish()
        device_id = self.heartbeat().json['device_id']
        self.client.post('/api/releases/activate', json={'version':'3.4.1','scope':'selected','device_ids':[device_id], 'window_start':'22:00','window_end':'06:00'})
        with patch.object(releases, 'in_window', return_value=False):
            self.assertIsNone(self.heartbeat().json['update'])
        self.assertIsNone(self.heartbeat(agent_version='3.5.0').json['update'])


    def test_download_refuses_redirects_and_incomplete_bytes(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.status_code = 302
        session = Mock()
        session.get.return_value = response
        with self.assertRaises(ValueError):
            atualizacao.download_package(session,'http://example.test',{},self.folder/'download.zip',100)
        response.status_code = 200
        response.iter_content.return_value = [b'short']
        with self.assertRaises(fixtures.requests.RequestException):
            atualizacao.download_package(session,'http://example.test',{},self.folder/'download.zip',100)
        self.assertFalse(session.get.call_args.kwargs['allow_redirects'])

    def test_msi_release_is_offered_only_to_msi_clients_and_downloads_verified_bytes(self):
        bundle, envelope = self.bundle(version='3.5.1', msi=True)
        response = self.client.post('/api/releases', data={'release': (io.BytesIO(bundle.read_bytes()), 'release.sti')})
        self.assertEqual(response.status_code, 201, response.json)
        self.heartbeat()
        self.assertEqual(self.client.post('/api/releases/activate', json={'version': '3.5.1'}).status_code, 200)
        self.assertIsNone(self.heartbeat(update_protocol=1).json['update'])
        self.assertEqual(self.heartbeat(update_protocol=2).json['update']['release'], envelope)
        response = self.client.get('/api/agent/releases/3.5.1/package',
            headers={**self.headers, 'X-Agent-ID': self.payload['agent_id']}, environ_overrides={'REMOTE_ADDR': self.ip})
        self.assertEqual(response.status_code, 200)
        self.assertIn('.msi', response.headers['Content-Disposition'])
        self.assertEqual(response.data, b'MZ-fixture-installer')
        self.assertIn('.msi', self.client.get('/api/releases/3.5.1/installer').headers['Content-Disposition'])
        with zipfile.ZipFile(bundle) as archive:
            self.assertEqual(sorted(archive.namelist()), ['installer.msi', 'manifest.json'])

    def test_msi_handoff_uses_windows_installer_without_exposing_token(self):
        self.root.mkdir(parents=True)
        _, envelope = self.bundle(version='3.5.1', msi=True)
        offer = {'release': envelope, 'rollout_id': str(uuid.uuid4())}
        def download(session, url, headers, path, size):
            Path(path).write_bytes(b'MZ-fixture-installer')
        with patch.object(atualizacao, 'installed_root', return_value=self.root), \
             patch.object(atualizacao, 'pending_offer', offer), patch.object(atualizacao, 'next_attempt', 0), \
             patch.object(atualizacao, 'report_progress'), patch.object(atualizacao, 'download_package', side_effect=download), \
             patch.object(atualizacao, 'verify_package') as verify, \
             patch.object(atualizacao, 'installation', return_value={'Startup': '0'}), \
             patch.object(atualizacao.subprocess, 'Popen') as launch:
            self.assertTrue(atualizacao.begin_update(Mock(), 'http://example.test', 'private-token',
                            self.payload['agent_id'], self.root/'sti-config.json'))
            arguments = launch.call_args.args[0]
            self.assertEqual(Path(arguments[0]).name, 'msiexec.exe')
            self.assertIn('/qn', arguments)
            self.assertIn('STI_STARTUP=0', arguments)
            self.assertNotIn('private-token', str(launch.call_args))
            verify.assert_called_once()
            self.assertEqual(list(self.root.parent.rglob('STI_Update.exe')), [])

    def test_health_acknowledgement_requires_target_version(self):
        self.root.mkdir(parents=True)
        with patch.object(atualizacao, 'installed_root', return_value=self.root), patch.object(atualizacao, 'health_sent', False):
            atualizacao.save_status(self.root, 'installing', atualizacao.AGENT_VERSION, 'rollout')
            atualizacao.acknowledge_health()
            self.assertEqual(protocol.read_json(atualizacao.state_path(self.root))['status'], 'updated')
        with patch.object(atualizacao, 'installed_root', return_value=self.root), patch.object(atualizacao, 'health_sent', False):
            atualizacao.save_status(self.root, 'installing', '9.0.0', 'rollout')
            atualizacao.acknowledge_health()
            self.assertEqual(protocol.read_json(atualizacao.state_path(self.root))['status'], 'failed')


    def test_transient_download_failure_can_retry_after_backoff(self):
        self.root.mkdir(parents=True)
        _, envelope = self.bundle(msi=True)
        offer = {'release': envelope, 'rollout_id': str(uuid.uuid4())}
        with patch.object(atualizacao, 'AGENT_VERSION', '3.4.0'), \
             patch.object(atualizacao, 'installed_root', return_value=self.root), patch.object(atualizacao, 'pending_offer', offer), \
             patch.object(atualizacao, 'next_attempt', 0), patch.object(atualizacao, 'report_progress'), \
             patch.object(atualizacao, 'download_package', side_effect=fixtures.requests.ConnectionError('offline')) as download, \
             self.assertLogs('STI_AGENT', level='ERROR'):
            self.assertFalse(atualizacao.begin_update(Mock(), 'http://example.test', 'token', self.payload['agent_id'], self.root/'sti-config.json'))
            self.assertTrue(protocol.read_json(atualizacao.state_path(self.root))['retryable'])
            atualizacao.next_attempt = 0
            self.assertFalse(atualizacao.begin_update(Mock(), 'http://example.test', 'token', self.payload['agent_id'], self.root/'sti-config.json'))
            self.assertEqual(download.call_count, 2)

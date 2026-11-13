"""Releases, assinatura e recuperação em diretórios temporários, sem registrar o Windows."""
import io
import json
import os
import uuid
import unittest
import zipfile
from datetime import datetime, timedelta
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

    def test_retention_lists_two_numeric_versions_and_removes_old_packages(self):
        for version in ('3.4.9', '3.4.10', '3.5.0'):
            self.publish(version)
        listed = self.client.get('/api/releases').json['releases']
        self.assertEqual([item['version'] for item in listed], ['3.5.0', '3.4.10'])
        root = releases.storage_path(server.DB_FILE)
        self.assertFalse((root/'3.4.9').exists())
        self.assertTrue((root/'3.4.10/installer.exe').is_file())
        self.assertTrue((root/'3.5.0/agent.zip').is_file())
        self.assertEqual(self.client.get('/api/releases/3.4.9/installer').status_code, 404)
        self.assertEqual(self.client.post('/api/releases/activate', json={'version': '3.4.9'}).status_code, 410)
        # A remoção dos pacotes não permite reutilizar um número já assinado.
        bundle, _ = self.bundle('3.4.9', content=b'MZ-changed-retired-release')
        response = self.client.post('/api/releases', data={'release': (io.BytesIO(bundle.read_bytes()), 'release.sti')})
        self.assertEqual(response.status_code, 400)

    def test_retention_preserves_active_distribution_until_paused(self):
        self.publish('3.4.1')
        self.client.post('/api/releases/activate', json={'version': '3.4.1'})
        self.publish('3.4.2')
        self.publish('3.5.0')
        root = releases.storage_path(server.DB_FILE)
        self.assertEqual(len(self.client.get('/api/releases').json['releases']), 2)
        download = self.client.get('/api/releases/3.4.1/installer')
        self.assertEqual(download.status_code, 200)
        download.close()
        self.assertEqual(self.heartbeat().json['update']['release']['manifest']['version'], '3.4.1')
        self.client.post('/api/releases/pause')
        self.assertFalse((root/'3.4.1').exists())

    def test_retention_preserves_recent_update_then_cleans_expired_attempt(self):
        self.publish('3.4.1')
        self.heartbeat(update_status={'status': 'downloading', 'target_version': '3.4.1'})
        self.publish('3.4.2')
        self.publish('3.5.0')
        root = releases.storage_path(server.DB_FILE)
        self.assertTrue((root/'3.4.1/agent.zip').is_file())
        with server.db_connect() as conn:
            conn.execute('UPDATE agent_update_state SET updated_at=?', ((datetime.now()-timedelta(hours=2)).isoformat(),))
        self.client.post('/api/releases/pause')
        self.assertFalse((root/'3.4.1').exists())

    def test_retention_does_not_follow_symlinks_or_remove_unknown_files(self):
        self.publish('3.4.1')
        root = releases.storage_path(server.DB_FILE)
        unrelated = root/'3.4.1/keep.txt'
        unrelated.write_text('Arquivo fora do pacote')
        self.publish('3.4.2')
        self.publish('3.5.0')
        self.assertTrue(unrelated.is_file())
        self.assertFalse((root/'3.4.1/agent.zip').exists())
        external = self.folder/'external'
        external.mkdir()
        (external/'installer.exe').write_bytes(b'unrelated')
        folder = root/'3.4.1'
        with patch.object(Path, 'resolve', autospec=True, side_effect=lambda path: external if path == folder else path.absolute()):
            with server.db_connect() as conn:
                releases.prune_release_files(conn, root)
        self.assertEqual((external/'installer.exe').read_bytes(), b'unrelated')

    def test_locked_old_package_does_not_fail_publication_and_cleanup_can_retry(self):
        self.publish('3.4.1')
        self.publish('3.4.2')
        root = releases.storage_path(server.DB_FILE)
        original_unlink = Path.unlink
        def locked_unlink(path, *args, **kwargs):
            if path == root/'3.4.1/installer.exe':
                raise PermissionError('Download aberto no Windows')
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', locked_unlink), self.assertLogs(releases.logger, level='WARNING'):
            self.publish('3.5.0')
        self.assertEqual(len(self.client.get('/api/releases').json['releases']), 2)
        self.assertTrue((root/'3.4.1/installer.exe').is_file())
        self.client.post('/api/releases/pause')
        self.assertFalse((root/'3.4.1').exists())


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

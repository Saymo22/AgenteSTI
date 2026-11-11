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
from sti.agente import atualizacao, instalacao
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

    def bundle(self, version='3.4.1', content=b'MZ-new-agent'):
        source = self.folder / ('source-' + version)
        source.mkdir(exist_ok=True)
        agent, installer = source / 'agent.exe', source / 'setup.exe'
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

    def install_fixture(self, version='3.4.0'):
        source = self.folder / 'old.exe'
        source.write_bytes(b'MZ-old-agent')
        with patch.object(instalacao, 'stop_installed_agent'):
            instalacao.install_agent(source, self.root, version, self.config, launch=False, register=False)

    def plan(self, envelope):
        staging = self.root.parent / 'updates' / str(uuid.uuid4())
        staging.mkdir(parents=True)
        package_source = self.folder / ('source-' + envelope['manifest']['version']) / 'out' / 'agent.zip'
        package = staging / 'agent.zip'
        package.write_bytes(package_source.read_bytes())
        plan = {'root': str(self.root), 'release': envelope, 'package': str(package),
                'previous_agent_hash': protocol.file_hash(self.root/'STI_Agente.exe'),
                'rollout_id': str(uuid.uuid4()), 'parent_pid': 1234567, 'config_file': str(self.root/'sti-config.json'),
                'nonce': str(uuid.uuid4()), 'health_file': str(staging/'health.json')}
        protocol.atomic_json(staging/'plan.json', plan)
        return staging/'plan.json', plan

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

    def test_install_upgrade_and_uninstall_preserve_configuration_and_identity(self):
        self.install_fixture()
        original_id = instalacao.installation_marker(self.root)['install_id']
        identity = self.root.parent/'identity.db'
        identity.write_bytes(b'persistent identity fixture')
        source = self.folder/'new.exe'
        source.write_bytes(b'MZ-new-agent')
        with patch.object(instalacao,'stop_installed_agent'):
            instalacao.install_agent(source,self.root,'3.4.1',{},launch=False,register=False)
            self.assertEqual(instalacao.installation_marker(self.root)['install_id'],original_id)
            self.assertEqual(protocol.read_json(self.root/'sti-config.json')['STI_AGENT_TOKEN'],self.config['STI_AGENT_TOKEN'])
            with self.assertRaises(ValueError):
                instalacao.install_agent(source,self.root,'3.4.0',{},launch=False,register=False)
            instalacao.remove_installation(self.root,unregister=False)
        self.assertTrue((self.root/'sti-config.json').exists())
        self.assertEqual(identity.read_bytes(),b'persistent identity fixture')
        self.assertFalse((self.root/'STI_Agente.exe').exists())

    def test_apply_update_confirms_health_and_keeps_backup(self):
        self.install_fixture()
        _, envelope = self.bundle()
        path, plan = self.plan(envelope)
        child = Mock()
        child.poll.return_value = None
        def launch(*args, **kwargs):
            protocol.atomic_json(plan['health_file'], {'nonce':plan['nonce'],'version':'3.4.1'})
            return child
        with patch.object(atualizacao.psutil,'Process') as process, patch.object(atualizacao,'launch_agent',side_effect=launch):
            process.return_value.wait.return_value = 0
            self.assertTrue(atualizacao.apply_plan(path,health_timeout=1))
        self.assertEqual((self.root/'STI_Agente.exe').read_bytes(),b'MZ-new-agent')
        self.assertEqual((self.root/'previous-agent.exe').read_bytes(),b'MZ-old-agent')
        self.assertEqual(protocol.read_json(atualizacao.state_path(self.root))['status'],'updated')

    def test_apply_update_rolls_back_when_new_agent_cannot_start(self):
        self.install_fixture()
        _, envelope = self.bundle()
        path, _ = self.plan(envelope)
        with patch.object(atualizacao.psutil,'Process') as process, patch.object(atualizacao,'launch_agent',side_effect=[OSError('Não iniciou'),Mock()]):
            process.return_value.wait.return_value = 0
            self.assertFalse(atualizacao.apply_plan(path,health_timeout=1))
        self.assertEqual((self.root/'STI_Agente.exe').read_bytes(),b'MZ-old-agent')
        self.assertEqual(instalacao.installation_marker(self.root)['version'],'3.4.0')
        self.assertEqual(protocol.read_json(atualizacao.state_path(self.root))['status'],'rolled_back')

    def test_apply_rejects_tampered_file_before_touching_installed_agent(self):
        self.install_fixture()
        _, envelope = self.bundle()
        path, plan = self.plan(envelope)
        Path(plan['package']).write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            atualizacao.apply_plan(path,health_timeout=0)
        self.assertEqual((self.root/'STI_Agente.exe').read_bytes(),b'MZ-old-agent')

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

    def test_helper_restarts_untouched_original_after_preflight_failure(self):
        self.install_fixture()
        _, envelope = self.bundle()
        path, plan = self.plan(envelope)
        Path(plan['package']).write_bytes(b'tampered after download')
        with patch.object(atualizacao.psutil, 'Process') as process, \
             patch.object(atualizacao, 'launch_agent') as launch, self.assertLogs('STI_AGENT', level='ERROR'):
            process.return_value.wait.return_value = 0
            self.assertFalse(atualizacao.run_update_helper(path))
            launch.assert_called_once_with(self.root.resolve(), config_file=plan['config_file'])
        self.assertEqual(protocol.read_json(atualizacao.state_path(self.root))['status'], 'failed')
        self.assertEqual((self.root/'STI_Agente.exe').read_bytes(), b'MZ-old-agent')

    def test_transient_download_failure_can_retry_after_backoff(self):
        self.install_fixture()
        _, envelope = self.bundle()
        offer = {'release': envelope, 'rollout_id': str(uuid.uuid4())}
        with patch.object(atualizacao, 'installed_root', return_value=self.root), patch.object(atualizacao, 'pending_offer', offer), \
             patch.object(atualizacao, 'next_attempt', 0), patch.object(atualizacao, 'report_progress'), \
             patch.object(atualizacao, 'download_package', side_effect=fixtures.requests.ConnectionError('offline')) as download, \
             self.assertLogs('STI_AGENT', level='ERROR'):
            self.assertFalse(atualizacao.begin_update(Mock(), 'http://example.test', 'token', self.payload['agent_id'], self.root/'sti-config.json'))
            self.assertTrue(protocol.read_json(atualizacao.state_path(self.root))['retryable'])
            atualizacao.next_attempt = 0
            self.assertFalse(atualizacao.begin_update(Mock(), 'http://example.test', 'token', self.payload['agent_id'], self.root/'sti-config.json'))
            self.assertEqual(download.call_count, 2)

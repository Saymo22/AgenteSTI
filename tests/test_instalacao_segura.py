"""Falhas de instalação e tráfego autenticado, sem processos ou rede reais."""
import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from requests.adapters import BaseAdapter
import test_integracao as fixtures
from sti.agente import instalacao
from sti.comum.releases import atomic_json, read_json


class RedirectAdapter(BaseAdapter):
    def __init__(self, status):
        self.status = status
        self.calls = []

    def send(self, request, **kwargs):
        self.calls.append(request)
        reply = requests.Response()
        reply.request, reply.url = request, request.url
        reply.raw, reply._content = io.BytesIO(b'{"ok":true}'), b'{"ok":true}'
        reply.status_code = self.status
        reply.headers['Location'] = 'http://other.invalid/collect'
        return reply

    def close(self):
        pass


class SafeInstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=fixtures.WORK)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / 'Agent'
        self.root.mkdir()

    def test_atomic_status_handles_concurrent_writers(self):
        destination = self.root/'state.json'
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda number: atomic_json(destination, {'id': number}), range(12)))
        self.assertIn(read_json(destination)['id'], range(12))
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_atomic_status_retries_transient_windows_lock(self):
        destination = self.root/'state.json'
        original = Path.replace
        attempts = []
        def replace(source, target):
            attempts.append(source)
            if len(attempts) == 1:
                raise PermissionError('temporary lock')
            return original(source, target)
        with patch.object(Path, 'replace', replace):
            atomic_json(destination, {'ok': True})
        self.assertEqual(len(attempts), 2)
        self.assertTrue(read_json(destination)['ok'])

    def test_authenticated_posts_never_follow_redirects(self):
        agent = fixtures.agente
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status), requests.Session() as session:
                session.trust_env = False
                adapter = RedirectAdapter(status)
                session.mount('http://', adapter)
                with patch.object(agent, 'API_URL', 'http://sti.invalid/api/agent'), \
                     patch.object(agent, 'STATUS_URL', 'http://sti.invalid/api/agent/command-status'), \
                     patch.object(agent, 'collect_identity', return_value={}):
                    self.assertFalse(agent.comunicar_servidor(session, {}))
                    with patch.object(agent.requests, 'post', side_effect=session.post):
                        self.assertFalse(agent.confirmar_comando('test-id', 'completed'))
                self.assertEqual(len(adapter.calls), 2)
                self.assertTrue(all(request.url.startswith('http://sti.invalid/') for request in adapter.calls))

    def test_legacy_process_requires_manual_close_without_terminating_anyone(self):
        current, owned, legacy, unrelated = Mock(), Mock(), Mock(), Mock()
        current.username.return_value = 'test-user'
        owned.info = {'exe': str(self.root/'STI_Agente.exe')}
        owned.username.return_value, owned.pid = 'test-user', 101
        legacy.info = {'exe': str(self.root.parent/'Portable'/'STI_Agente_V3_3.exe')}
        legacy.username.return_value, legacy.pid = 'test-user', 102
        unrelated.info = {'exe': str(self.root.parent/'other.exe')}
        unrelated.pid = 103
        with patch.object(instalacao.psutil, 'Process', return_value=current), \
             patch.object(instalacao.psutil, 'process_iter', return_value=[owned, unrelated, legacy]):
            with self.assertRaisesRegex(RuntimeError, 'Feche manualmente'):
                instalacao.stop_installed_agent(self.root, include_legacy=True)
        for process in (owned, legacy, unrelated):
            process.terminate.assert_not_called()

    def test_only_matching_installation_and_user_can_be_stopped(self):
        current, owned, other_user, unrelated = Mock(), Mock(), Mock(), Mock()
        current.username.return_value = 'test-user'
        for process, path, user, pid in ((owned, self.root/'STI_Agente.exe', 'test-user', 101),
                                        (other_user, self.root/'STI_Agente.exe', 'another-user', 102),
                                        (unrelated, self.root.parent/'other.exe', 'test-user', 103)):
            process.info, process.pid = {'exe': str(path)}, pid
            process.username.return_value = user
        with patch.object(instalacao.psutil, 'Process', return_value=current), \
             patch.object(instalacao.psutil, 'process_iter', return_value=[owned, other_user, unrelated]), \
             patch.object(instalacao.psutil, 'wait_procs', return_value=([], [])):
            instalacao.stop_installed_agent(self.root, include_legacy=True)
        owned.terminate.assert_called_once()
        other_user.terminate.assert_not_called()
        unrelated.terminate.assert_not_called()

    def test_early_agent_exit_is_not_reported_as_success(self):
        process = Mock()
        process.poll.return_value = 1
        with patch.object(instalacao, 'launch_agent', return_value=process):
            with self.assertRaisesRegex(RuntimeError, 'encerrou'):
                instalacao.confirm_agent_start(self.root, '3.4.1', timeout=1)
        self.assertEqual(list(self.root.glob('install-ready-*')), [])

    def test_local_start_requires_matching_version_and_nonce(self):
        process = Mock()
        process.poll.return_value = None
        def launch(root, env):
            atomic_json(env['STI_INSTALL_READY_FILE'], {'nonce': env['STI_INSTALL_READY_NONCE'], 'version': '3.4.1'})
            return process
        with patch.object(instalacao, 'launch_agent', side_effect=launch), patch.object(instalacao.time, 'sleep'):
            instalacao.confirm_agent_start(self.root, '3.4.1', timeout=1)
        self.assertEqual(list(self.root.glob('install-ready-*')), [])

    def test_mismatched_acknowledgement_is_rejected(self):
        process = Mock()
        process.poll.return_value = None
        def launch(root, env):
            atomic_json(env['STI_INSTALL_READY_FILE'], {'nonce': 'wrong', 'version': '3.4.1'})
            return process
        with patch.object(instalacao, 'launch_agent', side_effect=launch):
            with self.assertRaisesRegex(RuntimeError, 'não confirmou'):
                instalacao.confirm_agent_start(self.root, '3.4.1', timeout=.01)
        self.assertEqual(list(self.root.glob('install-ready-*')), [])

    def test_installer_propagates_start_failure_and_keeps_configuration(self):
        payload = self.root.parent/'source.exe'
        payload.write_bytes(b'MZ-test-only')
        config = {'STI_SERVER_IP': '10.2.116.121', 'STI_SERVER_PORT': 5000, 'STI_AGENT_TOKEN': 'test-secret-not-logged'}
        with patch.object(instalacao, 'stop_installed_agent'), \
             patch.object(instalacao, 'confirm_agent_start', side_effect=RuntimeError('test startup failure')), \
             self.assertLogs('STI_INSTALL', level='INFO') as logs:
            with self.assertRaisesRegex(RuntimeError, 'test startup failure'):
                instalacao.install_agent(payload, self.root, '3.4.1', config, register=False)
        output = '\n'.join(logs.output)
        self.assertIn('não foi confirmada', output)
        self.assertNotIn('Instalação concluída.', output)
        self.assertNotIn(config['STI_AGENT_TOKEN'], output)
        self.assertTrue((self.root/'sti-config.json').exists())

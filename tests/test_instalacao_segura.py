"""Falhas de instalação e tráfego autenticado, sem processos ou rede reais."""
import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

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

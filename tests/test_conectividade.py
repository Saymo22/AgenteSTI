"""Testa conectividade sem consultar a rede nem iniciar processos reais."""
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from sti.agente import conectividade as agent
from sti.comum import conectividade as contract


class ConnectivityTests(unittest.TestCase):
    def test_classification_distinguishes_ping_from_navigation(self):
        for ping, http, expected in [(True, True, 'available'), (False, True, 'available'),
                                     (True, False, 'limited'), (False, False, 'unavailable'),
                                     (None, False, 'unknown')]:
            with self.subTest(ping=ping, http=http), patch.object(agent, 'ping_external', return_value=ping), patch.object(agent, 'http_external', return_value=http):
                report = agent.probe()
                self.assertEqual(report['status'], expected)
                saved = contract.validate_report({**report, 'checked_ago_seconds': 2})
                self.assertEqual(contract.public_status(saved, True)['status'], expected)

    def test_windows_ping_does_not_accept_destination_unreachable(self):
        with patch.object(agent.platform, 'system', return_value='Windows'), patch.object(agent.subprocess, 'run') as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=b'Response: Destination host unreachable.')
            self.assertFalse(agent.ping_external())
            run.return_value.stdout = b'Reply from 8.8.8.8: bytes=32 time=10ms TTL=116'
            self.assertTrue(agent.ping_external())
            self.assertEqual(run.call_args.kwargs['timeout'], 3)
            self.assertNotIn('shell', run.call_args.kwargs)
            run.side_effect = subprocess.TimeoutExpired('ping', 3)
            self.assertFalse(agent.ping_external())
            run.side_effect = FileNotFoundError()
            self.assertIsNone(agent.ping_external())

    def test_http_requires_known_body_and_rejects_redirect_and_login_page(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(agent.requests, 'get', return_value=response) as get:
            for code, body, expected in [(200, agent.EXPECTED_BODY, True), (302, b'', False),
                                         (200, b'<html>Login</html>', False), (503, b'', False)]:
                response.status_code = code
                response.iter_content.return_value = iter([body])
                self.assertEqual(agent.http_external(), expected)
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            self.assertNotIn('X-Agent-Token', get.call_args.kwargs['headers'])
            get.side_effect = requests.Timeout()
            self.assertFalse(agent.http_external())

    def test_cache_never_runs_probe_in_telemetry_and_keeps_original_age(self):
        monitor = agent.InternetMonitor()
        with patch.object(agent, 'probe') as probe, patch.object(agent.time, 'monotonic', return_value=100):
            self.assertIsNone(monitor.report()['checked_ago_seconds'])
            monitor._sample = {'status': 'available', 'ping': True, 'http': True}
            monitor._checked = 30
            self.assertEqual(monitor.report()['checked_ago_seconds'], 70)
            probe.assert_not_called()

    def test_old_samples_and_offline_agents_never_appear_with_internet(self):
        report = contract.validate_report({'status':'available', 'ping':False, 'http':True, 'checked_ago_seconds':0})
        self.assertEqual(contract.public_status(report, False)['status'], 'unknown')
        report['checked_at'] = (datetime.now(timezone.utc) - timedelta(seconds=181)).isoformat()
        expired = contract.public_status(report, True)
        self.assertEqual(expired['status'], 'unknown')
        self.assertIsNotNone(expired['checked_at'])
        self.assertEqual(contract.public_status(None, True)['status'], 'unknown')

    def test_invalid_reports_rejected_and_old_agents_accepted(self):
        self.assertIsNone(contract.validate_report(None))
        self.assertIsNone(contract.validate_report({'status':'unknown', 'ping':None, 'http':None, 'checked_ago_seconds':None}))
        for changes in [{'status':[]}, {'status':'bad'}, {'http':'yes'}, {'ping':1},
                        {'status':'available', 'http':False}, {'checked_ago_seconds':True},
                        {'checked_ago_seconds':-1}, {'checked_ago_seconds':float('nan')},
                        {'checked_ago_seconds':float('inf')}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                contract.validate_report({'status':'available', 'ping':True, 'http':True, 'checked_ago_seconds':0, **changes})

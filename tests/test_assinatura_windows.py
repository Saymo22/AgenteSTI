"""Comandos de assinatura sem usar certificados ou rede reais."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.assinatura_windows import signing_options, sign_and_verify


class AuthenticodeTests(unittest.TestCase):
    def test_unsigned_mode_is_explicit_and_invalid_options_fail_early(self):
        self.assertIsNone(signing_options(None, None))
        with self.assertRaises(ValueError):
            signing_options(None, 'https://timestamp.example')
        with self.assertRaises(ValueError):
            signing_options('invalid', 'https://timestamp.example')
        with self.assertRaises(ValueError):
            signing_options('A'*40, 'https://user:password@timestamp.example')

    def test_signing_uses_existing_certificate_sha256_and_validates_trust(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.test-tmp') as folder:
            binary = Path(folder)/'agent.exe'
            binary.write_bytes(b'fixture')
            tool = Path(folder)/'signtool.exe'
            tool.write_bytes(b'fixture')
            options = signing_options('A'*40, 'https://timestamp.example', tool)
            with patch('scripts.assinatura_windows.subprocess.run') as run:
                sign_and_verify(binary, options)
            calls = [call.args[0] for call in run.call_args_list]
            self.assertEqual(calls[0][1:5], ['sign', '/sha1', 'A'*40, '/fd'])
            self.assertIn('SHA256', calls[0])
            self.assertEqual(calls[1][1:4], ['verify', '/pa', '/all'])
            self.assertTrue(all(call.kwargs['check'] for call in run.call_args_list))

    def test_rejected_signature_aborts_build(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.test-tmp') as folder:
            binary = Path(folder)/'agent.exe'
            binary.write_bytes(b'fixture')
            options = {'tool': 'signtool.exe', 'thumbprint': 'A'*40, 'timestamp_url': 'https://timestamp.example'}
            with patch('scripts.assinatura_windows.subprocess.run', side_effect=[None, subprocess.CalledProcessError(1, 'verify')]):
                with self.assertRaises(subprocess.CalledProcessError):
                    sign_and_verify(binary, options)

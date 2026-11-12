"""Regressões dos caminhos de configuração nos compiladores suportados."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sti.comum import empacotamento
from scripts.prova_nuitka import compiler_command

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_bundled_recognizes_both_compilers_and_preserves_source_mode(self):
        with patch.object(empacotamento.sys, 'frozen', False, create=True):
            self.assertFalse(empacotamento.is_bundled())
            with patch.object(empacotamento, '__compiled__', object(), create=True):
                self.assertTrue(empacotamento.is_bundled())
        with patch.object(empacotamento.sys, 'frozen', True, create=True):
            self.assertTrue(empacotamento.is_bundled())

    def test_config_next_to_executable_is_used_without_environment_override(self):
        script = '''
import json,sys
sys.path.insert(0,sys.argv[1])
from sti.comum import empacotamento
if sys.argv[3]=='nuitka': empacotamento.__dict__['__compiled__']=object()
else: sys.frozen=True
sys.executable=sys.argv[2]
sys.argv[0]=sys.argv[2]
from sti.comum.configuracao import CONFIG_FILE,setting
print(json.dumps({'file':str(CONFIG_FILE),'server':setting('STI_SERVER_IP')}))
'''
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-tmp') as folder:
            base = Path(folder).resolve()
            (base/'sti-config.json').write_text('{"STI_SERVER_IP":"127.0.0.77"}', encoding='utf-8')
            env = {key:value for key,value in os.environ.items() if not key.startswith('STI_')}
            for compiler in ('nuitka', 'pyinstaller'):
                result = subprocess.run([sys.executable, '-c', script, str(ROOT), str(base/'STI_Agente.exe'), compiler],
                                        cwd=ROOT/'tests', env=env, capture_output=True, text=True, check=True, timeout=15)
                info = json.loads(result.stdout)
                self.assertEqual(Path(info['file']), base/'sti-config.json')
                self.assertEqual(info['server'], '127.0.0.77')

    def test_nuitka_onefile_uses_original_filename_for_config_and_self_copy(self):
        original = ROOT/'dist'/'STI_Update.exe'
        with patch.object(empacotamento, '__compiled__', object(), create=True), \
             patch.object(empacotamento.sys, 'executable', str(ROOT/'build'/'temporary.exe')), \
             patch.object(empacotamento.sys, 'argv', [str(original), '--apply-update', 'plan.json']):
            self.assertEqual(empacotamento.executable_path(), original)

    def test_resources_use_pyinstaller_extraction_or_compiled_module_directory(self):
        with patch.object(empacotamento.sys, '_MEIPASS', 'test-extracted', create=True):
            self.assertEqual(empacotamento.resource_directory('anything.py'), Path('test-extracted'))
        self.assertEqual(empacotamento.resource_directory(ROOT/'packaging/instalador.py'), ROOT/'packaging')

    def test_experimental_build_is_separate_and_contains_only_public_key(self):
        command = compiler_command('agente', 'standalone', ROOT/'dist/compatibilidade/test', 'mingw64', 2)
        joined = '\n'.join(command)
        self.assertIn('--mode=standalone', command)
        self.assertIn('--windows-console-mode=force', command)
        self.assertIn('--include-module=win32ts', command)
        self.assertIn('release-public-key.pem', joined)
        self.assertNotIn('agent-signing-key.pem', joined)
        self.assertNotIn('sti-config.json', joined)

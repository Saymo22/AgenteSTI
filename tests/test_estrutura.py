"""Regressões dos caminhos e pontos de entrada após a organização dos fontes."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StructureTests(unittest.TestCase):
    def test_original_entry_points_delegate_to_packages(self):
        import app
        import agente
        import preparar_config
        from sti.servidor import app as server
        from sti.agente import cliente
        from scripts.preparar_config import preparar

        self.assertIs(app.app, server.app)
        self.assertIs(app.create_app, server.create_app)
        self.assertIs(agente.main, cliente.main)
        self.assertIs(preparar_config.preparar, preparar)

    def test_paths_are_independent_of_working_directory(self):
        script = """
import json,sys
sys.path.insert(0, sys.argv[1])
from sti.comum.configuracao import BASE_DIR
from sti.servidor.app import app
from scripts.preparar_config import preparar
print(json.dumps({'base':str(BASE_DIR), 'web':app.root_path}))
"""
        result = subprocess.run(
            [sys.executable, '-c', script, str(ROOT)], cwd=ROOT / 'tests',
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, check=True, timeout=15
        )
        paths = json.loads(result.stdout)
        self.assertEqual(Path(paths['base']), ROOT)
        self.assertEqual(Path(paths['web']), ROOT / 'sti' / 'servidor')
        self.assertTrue((Path(paths['web']) / 'templates' / 'index.html').is_file())
        self.assertTrue((Path(paths['web']) / 'static' / 'painel.js').is_file())


if __name__ == '__main__':
    unittest.main()

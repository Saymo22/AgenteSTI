"""Validação de produto MSI e preservação da configuração, sem instalar produtos."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_integracao import WORK

from sti.agente import msi
from sti.comum.msi import UPGRADE_CODE, product_code, msi_version
from sti.comum.releases import atomic_json, read_json


class MsiTests(unittest.TestCase):
    def test_product_identity_changes_only_with_version_and_limits_are_enforced(self):
        self.assertEqual(product_code('3.5.0'), product_code('3.5.0'))
        self.assertNotEqual(product_code('3.5.0'), product_code('3.5.1'))
        for version in ('256.0.0', '1.256.0', '1.0.65536', '3.5', '../../file'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                msi_version(version)

    def test_rejects_other_product_version_scope_or_product_code(self):
        properties = {'UpgradeCode': UPGRADE_CODE, 'ProductCode': product_code('3.5.1'), 'ProductVersion': '3.5.1'}
        with patch.object(msi, 'package_properties', return_value=properties):
            msi.verify_package('test.msi', '3.5.1')
        for key, value in (('UpgradeCode', 'other'), ('ProductCode', 'other'), ('ProductVersion', '3.5.2'), ('ALLUSERS', '1')):
            with patch.object(msi, 'package_properties', return_value={**properties, key: value}), self.assertRaises(ValueError):
                msi.verify_package('test.msi', '3.5.1')

    def test_restarted_agent_owns_its_extraction_directory(self):
        root = Path('test-install').resolve()
        with patch('sti.comum.empacotamento.executable_path', return_value=root/'STI_Agente.exe'), \
             patch.object(msi.subprocess, 'Popen') as launch:
            msi.launch()
        self.assertEqual(launch.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        self.assertEqual(launch.call_args.kwargs['env']['STI_CONFIG_FILE'], str(root/'sti-config.json'))

    @unittest.skipUnless(sys.platform == 'win32', 'Registro Windows')
    def test_configuration_preserved_and_server_secrets_rejected(self):
        import winreg
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            root = Path(folder)/'Agent'
            root.mkdir()
            source = Path(folder)/'agent-config.json'
            config = {'STI_SERVER_IP': '10.2.116.110', 'STI_AGENT_TOKEN': 'fixture-token'}
            atomic_json(source, config)
            with patch('sti.agente.instalacao.configure_install_logging'), patch.object(winreg, 'OpenKey', side_effect=FileNotFoundError):
                msi.configure(root, '', str(Path(folder)/'agent.msi'))
                original = (root/'sti-config.json').read_bytes()
                atomic_json(source, {'STI_ADMIN_PASSWORD': 'never-copy-this'})
                msi.configure(root, str(source))
                self.assertEqual((root/'sti-config.json').read_bytes(), original)
                (root/'sti-config.json').unlink()
                with self.assertRaises(ValueError):
                    msi.configure(root, str(source))
                self.assertFalse((root/'sti-config.json').exists())

    @unittest.skipUnless(sys.platform == 'win32' and sys.version_info[:2] == (3, 12), 'Autor MSI Windows/Python 3.12')
    def test_real_msi_has_single_payload_and_native_registration(self):
        import msilib
        from scripts.msi import build_msi
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            path = build_msi(sys.executable, Path(folder)/'test.msi', '3.5.1')
            msi.verify_package(path, '3.5.1')
            db = msilib.OpenDatabase(str(path), msilib.MSIDBOPEN_READONLY)
            view = db.OpenView('SELECT `FileName` FROM `File`')
            view.Execute(None)
            self.assertIn('STI_Agente.exe', view.Fetch().GetString(1))
            self.assertIsNone(view.Fetch())
            self.assertEqual(db.GetSummaryInformation(0).GetProperty(15), 10)
            view.Close()
            view = db.OpenView('SELECT `Action`, `Sequence` FROM `InstallExecuteSequence`')
            view.Execute(None)
            actions = {}
            while record := view.Fetch():
                actions[record.GetString(1)] = record.GetInteger(2)
            self.assertLess(actions['InstallExecute'], actions['RemoveExistingProducts'])
            self.assertLess(actions['RemoveExistingProducts'], actions['InstallFinalize'])
            view.Close()
            del view, db

"""Serviço e migração sem instalar ou parar serviços reais da estação de desenvolvimento."""
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from contextlib import ExitStack, closing
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from test_integracao import WORK, agente
from sti.agente import migracao_servico as migration
from sti.comum import servico as paths
from sti.comum.releases import atomic_json, read_json


@unittest.skipUnless(sys.platform == 'win32', 'Serviço Windows')
class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=WORK)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.env = patch.dict(os.environ, {'PROGRAMDATA':str(self.root/'data'), 'ProgramW6432':str(self.root/'programs')})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.install = self.root/'programs/STI/AgentService'
        self.install.mkdir(parents=True)
        self.legacy = self.root/'user/STI/Agent'
        self.legacy.mkdir(parents=True)
        self.config = {'STI_SERVER_IP':'10.2.116.110','STI_AGENT_TOKEN':'fixture-token'}
        atomic_json(self.legacy/'sti-config.json', self.config)
        self.identity = str(uuid.uuid4())
        with closing(sqlite3.connect(self.legacy.parent/'identity.db')) as conn, conn:
            conn.execute('CREATE TABLE identity (id INTEGER PRIMARY KEY,agent_id TEXT,hardware_key TEXT,key_kind TEXT)')
            conn.execute('INSERT INTO identity VALUES (1,?,?,?)', (self.identity,'a'*64,'smbios'))
        self.protect = patch.object(migration, 'protect_directory', side_effect=lambda root:root.mkdir(parents=True,exist_ok=True))
        self.real_protect = migration.protect_directory
        self.protect.start()
        self.addCleanup(self.protect.stop)
        self.logging = patch('sti.agente.instalacao.configure_install_logging')
        self.logging.start()
        self.addCleanup(self.logging.stop)

    def test_migration_preserves_identity_and_config_and_never_executes_old_binary(self):
        with patch('subprocess.Popen') as launch:
            migration.configure_service(self.install, legacy_root=str(self.legacy),user_sid='S-1-5-21-1000')
            launch.assert_not_called()
        saved = read_json(paths.data_dir()/'sti-config.json')
        self.assertEqual(saved['STI_AGENT_TOKEN'], self.config['STI_AGENT_TOKEN'])
        self.assertEqual(saved['STI_IDENTITY_FILE'], str(paths.data_dir()/'identity.db'))
        self.assertEqual(migration.read_identity(paths.data_dir()/'identity.db')[0],self.identity)
        self.assertTrue(read_json(paths.data_dir()/'migration.json')['pending'])
        self.assertTrue((self.legacy/'sti-config.json').exists())
        atomic_json(self.root/'bad.json', {'STI_ADMIN_PASSWORD':'not-an-agent-config'})
        migration.configure_service(self.install, str(self.root/'bad.json'))
        self.assertEqual(read_json(paths.data_dir()/'sti-config.json'),saved)

    def test_missing_identity_never_silently_creates_a_new_inventory(self):
        (self.legacy.parent/'identity.db').unlink()
        with self.assertRaises(ValueError):
            migration.configure_service(self.install,legacy_root=str(self.legacy))
        self.assertFalse((paths.data_dir()/'sti-config.json').exists())

    def test_deleted_legacy_config_can_use_config_next_to_msi_preserving_identity(self):
        (self.legacy/'sti-config.json').unlink()
        download = self.root/'download'
        download.mkdir()
        atomic_json(download/'agent-config.json',self.config)
        migration.configure_service(self.install,original_database=str(download/'agent.msi'),legacy_root=str(self.legacy))
        self.assertEqual(migration.read_identity(paths.data_dir()/'identity.db')[0],self.identity)
        self.assertEqual(read_json(paths.data_dir()/'sti-config.json')['STI_SERVER_IP'],self.config['STI_SERVER_IP'])

    def test_explicit_missing_configuration_is_not_silently_replaced(self):
        with self.assertRaises(ValueError):
            migration.configure_service(self.install,config_source=str(self.root/'missing.json'),legacy_root=str(self.legacy))
        self.assertFalse((paths.data_dir()/'sti-config.json').exists())

    def test_nonprotected_installation_directory_is_rejected(self):
        with self.assertRaises(ValueError):
            migration.configure_service(self.root/'user/writable')
        self.assertFalse(paths.data_dir().exists())

    def test_data_precreated_by_normal_user_is_not_promoted_to_system_configuration(self):
        untrusted = self.root/'untrusted-service-data'
        untrusted.mkdir()
        atomic_json(untrusted/'sti-config.json',self.config)
        with self.assertRaises(ValueError):
            self.real_protect(untrusted)
        self.assertEqual(read_json(untrusted/'sti-config.json'),self.config)

    def test_pending_commands_are_preserved_without_reexecuting_uncertain_actions(self):
        command_id = str(uuid.uuid4())
        with closing(sqlite3.connect(self.legacy.parent/'commands.db')) as conn, conn:
            conn.execute('CREATE TABLE journal_identity (id INTEGER PRIMARY KEY,agent_id TEXT)')
            conn.execute('INSERT INTO journal_identity VALUES (1,?)',(self.identity,))
            conn.execute('CREATE TABLE jobs (id TEXT,command TEXT,message TEXT,stage TEXT,status TEXT,result TEXT,updated_at REAL)')
            conn.execute('INSERT INTO jobs VALUES (?,?,?, ?,?,?,?)',(command_id,'restart','','running','','',1))
        migration.configure_service(self.install,legacy_root=str(self.legacy))
        with closing(sqlite3.connect(paths.data_dir()/'commands.db')) as conn:
            self.assertEqual(conn.execute('SELECT id,stage,status FROM jobs').fetchone(),(command_id,'result','failed'))
            self.assertEqual(conn.execute('SELECT agent_id FROM journal_identity').fetchone()[0],self.identity)

    def test_environment_is_independent_of_logged_in_user(self):
        with patch.dict(os.environ):
            paths.prepare_environment()
            self.assertTrue(paths.service_mode())
            self.assertEqual(os.environ['STI_CONFIG_FILE'],str(paths.data_dir()/'sti-config.json'))
            self.assertEqual(os.environ['STI_IDENTITY_FILE'],str(paths.data_dir()/'identity.db'))

    def test_old_startup_is_removed_only_after_service_started_and_path_matches(self):
        import winreg
        context = MagicMock()
        with patch.object(migration,'win32serviceutil_status',return_value=4), \
             patch.object(winreg,'QueryInfoKey',return_value=(0,0,0)), \
             patch.object(winreg,'OpenKey',return_value=context), \
             patch.object(winreg,'QueryValueEx',side_effect=[(str(self.legacy),1),('"'+str(self.legacy/'STI_Agente.exe')+'"',1)]), \
             patch.object(winreg,'DeleteValue') as remove, patch('psutil.process_iter',return_value=[]):
            paths.data_dir().mkdir(parents=True)
            migration.commit_migration(str(self.legacy),'S-1-5-21-1000')
            remove.assert_called_once()
            self.assertFalse(read_json(paths.data_dir()/'migration.json')['pending'])
        with patch.object(migration,'win32serviceutil_status',return_value=1), \
             patch.object(winreg,'OpenKey') as registry:
            migration.commit_migration(str(self.legacy),'S-1-5-21-1000')
            registry.assert_not_called()

    def test_another_installation_path_is_not_modified(self):
        import winreg
        with patch.object(migration,'win32serviceutil_status',return_value=4), \
             patch.object(winreg,'QueryInfoKey',return_value=(0,0,0)), \
             patch.object(winreg,'OpenKey',return_value=MagicMock()), \
             patch.object(winreg,'QueryValueEx',return_value=(str(self.root/'other'),1)), \
             patch.object(winreg,'DeleteValue') as remove, patch('psutil.process_iter') as processes:
            migration.commit_migration(str(self.legacy),'S-1-5-21-1000')
            remove.assert_not_called()
            processes.assert_not_called()


@unittest.skipUnless(sys.platform == 'win32', 'Serviço Windows')
class ServiceRuntimeTests(unittest.TestCase):
    def test_dispatcher_hosts_service_and_stop_signals_worker(self):
        from sti.agente import servico
        with patch.dict(os.environ), patch.object(servico.servicemanager,'Initialize'), \
             patch.object(servico.servicemanager,'PrepareToHostSingle') as host, \
             patch.object(servico.servicemanager,'StartServiceCtrlDispatcher') as dispatcher:
            servico.run()
            host.assert_called_once_with(servico.AgentService)
            dispatcher.assert_called_once()
        service = object.__new__(servico.AgentService)
        service.stop_event = threading.Event()
        service.ReportServiceStatus = Mock()
        service.SvcStop()
        self.assertTrue(service.stop_event.is_set())

    def test_startup_failure_is_reported_but_update_exit_is_planned(self):
        from sti.agente import servico
        service = object.__new__(servico.AgentService)
        service.stop_event = threading.Event()
        with patch.dict(os.environ), patch.object(agente,'iniciar_agente',return_value=None):
            with self.assertRaises(RuntimeError):
                service.SvcDoRun()
        with patch.dict(os.environ), patch.object(agente,'iniciar_agente',return_value=True):
            service.SvcDoRun()

    def test_message_is_delivered_to_active_session_and_rejected_without_user(self):
        import win32ts
        from sti.agente.servico import send_message
        with patch.object(win32ts,'WTSEnumerateSessions',return_value=[]), patch.object(win32ts,'WTSSendMessage') as send:
            self.assertEqual(send_message('Teste')[0],'rejected')
            send.assert_not_called()
        with patch.object(win32ts,'WTSEnumerateSessions',return_value=[{'SessionId':5,'State':win32ts.WTSActive}]), \
             patch.object(win32ts,'WTSGetActiveConsoleSessionId',return_value=5), \
             patch.object(win32ts,'WTSSendMessage',return_value=1) as send:
            self.assertEqual(send_message('Teste')[0],'completed')
            self.assertEqual(send.call_args.args[1],5)
            self.assertEqual(send.call_args.args[-2:],(30,True))

    def test_stop_interrupts_retry_wait_without_network_or_hardware_calls(self):
        stop, attempted = threading.Event(), threading.Event()
        with ExitStack() as stack:
            for name,value in [('validar_configuracoes',True),('verificar_instancia_unica',True),
                               ('persistent_identity','fixture-id'),('obter_hostname','PC-TESTE'),('obter_usuario',''),
                               ('init_journal',None),('diagnosticar_rede',False),('coletar_dados',{}),('service_mode',True)]:
                stack.enter_context(patch.object(agente,name,return_value=value))
            stack.enter_context(patch.object(agente.conectividade.monitor,'start'))
            stack.enter_context(patch.object(migration,'retry_migration'))
            stack.enter_context(patch.object(agente,'comunicar_servidor',side_effect=lambda *args:attempted.set() or False))
            worker = threading.Thread(target=agente.iniciar_agente,args=(stop,))
            worker.start()
            try:
                self.assertTrue(attempted.wait(2))
            finally:
                stop.set()
                worker.join(2)
            self.assertFalse(worker.is_alive())

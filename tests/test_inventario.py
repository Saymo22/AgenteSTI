"""Identidade, DHCP, reinstalação e isolamento de comandos; somente bancos temporários."""
import json
import uuid
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch

import test_integracao as fixtures
from sti.servidor import app as server
from sti.agente import identidade


class InventoryTests(unittest.TestCase):
    def setUp(self):
        fixtures.IntegrationTests.setUp(self)
        self.payload.update(agent_id=str(uuid.uuid4()),instance_id=str(uuid.uuid4()),hardware_key='a'*64,
            serial_number='SERIE-123',mac_addresses=['02-11-22-33-44-55'],manufacturer='Fabricante',model='Estação')

    def heartbeat(self, payload=None, ip=None):
        return fixtures.IntegrationTests.heartbeat(self,payload,ip)

    def items(self):
        response = self.client.get('/api/devices')
        self.assertEqual(response.status_code,200)
        return response.json['devices']

    def organization(self, reference, **changes):
        return self.client.patch(f'/api/devices/{reference}/organization',json=changes)

    def command(self):
        device_id=server.devices[self.ip].get('device_id')
        return self.client.post(f'/api/command/{self.ip}',json={'command':'msg','message':'Teste','device_id':device_id})

    def age(self, device_id):
        with server.db_connect() as conn:
            conn.execute('UPDATE machine_inventory SET last_agent_seen=? WHERE device_id=?',
                ((datetime.now()-timedelta(seconds=server.OFFLINE_THRESHOLD+10)).isoformat(),device_id))

    def test_mac_changes_and_dhcp_preserve_identity_organization_and_history(self):
        self.assertEqual(self.heartbeat().status_code,200)
        device_id=self.items()[0]['device_id']
        self.assertNotEqual(device_id,self.payload['agent_id'])
        self.organization(device_id,department='TI',room='Sala 1',responsible='Ana',display_name='PC da Ana',platform='Windows')
        previous=dict(server.devices[self.ip])
        for ip in ('10.2.117.33','10.2.118.33','10.2.119.33'):
            response=self.heartbeat({**self.payload,'mac_addresses':['02:AA:BB:CC:DD:EE']},ip)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['device_id'],device_id)
        server.save_device(self.ip,previous)  # Scanner antigo não recria o vínculo antigo.
        items=self.items()
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['ip'],'10.2.119.33')
        self.assertEqual(items[0]['organization']['responsible'],'Ana')
        self.assertEqual(items[0]['organization']['display_name'],'PC da Ana')
        self.assertEqual(items[0]['organization']['platform'],'Windows')
        self.assertEqual(items[0]['mac_addresses'],['02:AA:BB:CC:DD:EE'])
        history=self.client.get(f'/api/events?device_id={device_id}').json['events']
        self.assertEqual(sum(e['status']=='ip_alterado' for e in history),3)
        server.devices.clear()
        server.load_devices()
        self.assertEqual(self.items()[0]['device_id'],device_id)
        self.assertFalse(self.items()[0]['agent_online'])

    def test_upgrade_adopts_legacy_once_and_expires_legacy_commands(self):
        legacy={key:value for key,value in self.payload.items() if key not in
            ('agent_id','instance_id','hardware_key','serial_number','mac_addresses','manufacturer','model')}
        self.assertEqual(self.heartbeat(legacy).status_code,200)
        self.organization(self.ip,department='Financeiro',display_name='PC financeiro',platform='Windows')
        job=self.command().json['command_id']
        self.assertEqual(self.heartbeat().status_code,200)
        item=self.items()[0]
        self.assertEqual(item['organization']['department'],'Financeiro')
        self.assertEqual(item['organization']['display_name'],'PC financeiro')
        self.assertEqual(item['organization']['platform'],'Windows')
        self.assertEqual(server.get_command(job)['status'],'expired')
        self.assertEqual(self.heartbeat(legacy).status_code,409)
        with server.db_connect() as conn:
            self.assertFalse(conn.execute('SELECT 1 FROM device_organization WHERE ip=?',(self.ip,)).fetchone())

    def test_ip_reuse_archives_previous_machine_and_does_not_inherit_its_data(self):
        self.heartbeat()
        old_id=self.items()[0]['device_id']
        self.organization(old_id,department='RH',room='104')
        stale=dict(server.devices[self.ip])
        job=self.command().json['command_id']
        new={**self.payload,'agent_id':str(uuid.uuid4()),'instance_id':str(uuid.uuid4()),'hardware_key':'b'*64,'name':'PC-NOVO'}
        self.assertEqual(self.heartbeat(new).status_code,200)
        server.save_device(self.ip,stale)
        old,new_item=sorted(self.items(),key=lambda d:d['device_id']!=old_id)
        self.assertFalse(old['address_active'])
        self.assertFalse(old['online'])
        self.assertEqual(old['organization']['department'],'RH')
        self.assertEqual(new_item['organization']['department'],'')
        self.assertNotEqual(new_item['device_id'],old_id)
        self.assertEqual(server.get_command(job)['status'],'expired')
        self.organization(old_id,room='105')
        self.assertEqual(next(d for d in self.items() if d['device_id']==old_id)['organization']['room'],'105')
        server.devices.clear()
        server.load_devices()
        self.assertEqual(len(self.items()),2)

    def test_cloned_uuid_conflicts_do_not_replace_the_registered_machine(self):
        self.heartbeat()
        device_id=self.items()[0]['device_id']
        self.organization(device_id,department='TI')
        job=self.command().json['command_id']
        for _ in range(2):
            response=self.heartbeat({**self.payload,'hardware_key':'b'*64,'name':'CLONE'},'10.2.117.44')
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json['code'],'identity_conflict')
        self.assertEqual(len(self.items()),1)
        self.assertEqual(self.items()[0]['name'],'PC-TESTE')
        self.assertEqual(server.get_command(job)['status'],'queued')
        data=self.client.get('/api/devices').json
        self.assertEqual(len(data['identity_conflicts']),1)
        self.assertEqual(self.heartbeat({**self.payload,'instance_id':str(uuid.uuid4())},'10.2.117.44').status_code,409)
        self.assertEqual(self.heartbeat(ip='10.2.117.44').status_code,200)

    def test_commands_require_expected_device_and_confirmation_identity(self):
        self.heartbeat()
        self.assertEqual(self.client.post(f'/api/command/{self.ip}',json={'command':'msg','message':'Teste'}).status_code,409)
        job=self.command().json['command_id']
        self.assertEqual(self.heartbeat().json['command_id'],job)
        endpoint='/api/agent/command-status'
        base={'id':job,'status':'accepted'}
        self.assertEqual(self.client.post(endpoint,json=base,headers=self.headers,environ_overrides={'REMOTE_ADDR':self.ip}).status_code,409)
        valid={**base,'agent_id':self.payload['agent_id'],'instance_id':self.payload['instance_id'],'hardware_key':self.payload['hardware_key']}
        self.assertEqual(self.client.post(endpoint,json=valid,headers=self.headers,environ_overrides={'REMOTE_ADDR':self.ip}).status_code,200)
        self.heartbeat(ip='10.2.117.44')
        self.assertEqual(server.get_command(job)['status'],'expired')

    def test_reinstallation_recovery_is_explicit_and_preserves_previous_inventory(self):
        self.heartbeat()
        target=self.items()[0]['device_id']
        self.organization(target,department='RH',room='101',responsible='Ana',display_name='RH da Ana',platform='Windows')
        self.age(target)
        replacement={**self.payload,'agent_id':str(uuid.uuid4()),'instance_id':str(uuid.uuid4()),'name':'REINSTALADO'}
        source=self.heartbeat(replacement,'10.2.117.44').json['device_id']
        self.assertNotEqual(source,target)
        item=next(d for d in self.items() if d['device_id']==source)
        self.assertEqual(item['organization']['department'],'')
        self.assertEqual(item['recovery_candidates'][0]['device_id'],target)
        endpoint=f'/api/inventory/{source}/reconcile'
        self.assertEqual(server.app.test_client().post(endpoint,json={}).status_code,401)
        response=self.client.post(endpoint,json={'target_device_id':target,'expected_agent_id':replacement['agent_id']})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(len(self.items()),1)
        self.assertEqual(self.items()[0]['organization']['responsible'],'Ana')
        self.assertEqual(self.items()[0]['organization']['display_name'],'RH da Ana')
        self.assertEqual(self.items()[0]['organization']['platform'],'Windows')
        self.assertEqual(self.items()[0]['device_id'],target)
        self.assertEqual(self.heartbeat(replacement,'10.2.117.44').json['device_id'],target)
        self.assertEqual(self.heartbeat().status_code,409)  # UUID anterior não volta a tomar posse do cadastro.
        history=self.client.get(f'/api/events?device_id={target}').json['events']
        self.assertTrue(any(e['status']=='instalacao_recuperada' for e in history))

    def test_recovery_rejects_active_target_or_different_hardware(self):
        self.heartbeat()
        target=self.items()[0]['device_id']
        replacement={**self.payload,'agent_id':str(uuid.uuid4()),'instance_id':str(uuid.uuid4())}
        source=self.heartbeat(replacement,'10.2.117.44').json['device_id']
        endpoint=f'/api/inventory/{source}/reconcile'
        body={'target_device_id':target,'expected_agent_id':replacement['agent_id']}
        self.assertEqual(self.client.post(endpoint,json=body).status_code,409)
        self.age(target)
        self.heartbeat({**replacement,'hardware_key':'b'*64},'10.2.117.44')  # Recusado; hardware original preservado.
        with server.db_connect() as conn:
            conn.execute('UPDATE machine_inventory SET hardware_key=?,mac_addresses=? WHERE device_id=?',('b'*64,'[]',source))
        self.assertEqual(self.client.post(endpoint,json=body).status_code,409)

    def test_recovery_by_serial_and_mac_requires_administrator_confirmation(self):
        self.heartbeat()
        target=self.items()[0]['device_id']
        self.age(target)
        replacement={**self.payload,'agent_id':str(uuid.uuid4()),'instance_id':str(uuid.uuid4()),'hardware_key':'b'*64}
        source=self.heartbeat(replacement,'10.2.117.44').json['device_id']
        self.assertEqual(len(self.items()),2)
        item=next(d for d in self.items() if d['device_id']==source)
        self.assertEqual(item['recovery_candidates'][0]['device_id'],target)
        reply=self.client.post(f'/api/inventory/{source}/reconcile',json={'target_device_id':target,'expected_agent_id':replacement['agent_id']})
        self.assertEqual(reply.status_code,200)

    def test_identity_filtered_reports_include_events_across_addresses(self):
        self.heartbeat()
        device_id=self.items()[0]['device_id']
        self.heartbeat(ip='10.2.117.44')
        response=self.client.get(f'/api/report/events.csv?device_id={device_id}')
        self.assertEqual(response.status_code,200)
        self.assertIn('10.2.116.33',response.get_data(as_text=True))
        self.assertIn('10.2.117.44',response.get_data(as_text=True))
        self.assertEqual(self.client.get('/api/events?device_id=invalido').status_code,400)
        self.assertEqual(self.client.get('/relatorios?device_id=invalido').status_code,400)

    def test_local_commands_from_another_identity_are_not_replayed(self):
        agent=fixtures.agente
        agent.init_journal('installation-one')
        with patch.object(agent,'retry_pending_commands'):
            agent.processar_comando({'command_id':'old-job','command':'msg','message':'Teste'})
        agent.init_journal('installation-two')
        with agent.journal_connect() as conn:
            self.assertEqual(conn.execute('SELECT stage,status FROM jobs WHERE id=?',('old-job',)).fetchone(),('acknowledged','rejected'))

    def test_invalid_identity_does_not_mutate_inventory(self):
        self.heartbeat()
        for field,value in [('agent_id',''),('agent_id',None),('instance_id',[]),('hardware_key','z'*64),
                            ('mac_addresses',['00:00:00:00:00:00']),('mac_addresses','texto'),('serial_number',[]),('model','a\nb')]:
            self.assertEqual(self.heartbeat({**self.payload,field:value}).status_code,400,(field,value))
        self.assertEqual(len(self.items()),1)

    def test_old_scanner_snapshot_does_not_overwrite_permanent_inventory(self):
        self.heartbeat()
        device_id=self.items()[0]['device_id']
        old=dict(server.devices[self.ip])
        self.heartbeat({**self.payload,'cpu':44})
        old['last_seen']-=timedelta(days=1)
        old['hw']={'cpu':99}
        server.save_device(self.ip,old)
        with server.db_connect() as conn:
            snapshot=json.loads(conn.execute('SELECT snapshot FROM machine_inventory WHERE device_id=?',(device_id,)).fetchone()[0])
        self.assertEqual(snapshot['hw']['cpu'],44)

    def test_concurrent_address_changes_keep_one_identity(self):
        self.heartbeat()
        device_id=self.items()[0]['device_id']
        def send(ip):
            with server.app.test_client() as client:
                return client.post('/api/agent',json=self.payload,headers=self.headers,environ_overrides={'REMOTE_ADDR':ip}).status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses=list(pool.map(send,['10.2.116.44','10.2.117.44','10.2.118.44','10.2.119.44']))
        self.assertEqual(responses,[200]*4)
        self.assertEqual(len(self.items()),1)
        self.assertEqual(self.items()[0]['device_id'],device_id)


class AgentIdentityTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.temp=tempfile.TemporaryDirectory(dir=fixtures.WORK)
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'identity.db'

    def test_uuid_survives_restart_and_changes_when_copied_to_other_hardware(self):
        first=identidade.load_identity(self.path,'a'*64)
        self.assertEqual(first,identidade.load_identity(self.path,'a'*64))
        self.assertEqual(first,identidade.load_identity(self.path,''))  # Falha temporária de coleta.
        second=identidade.load_identity(self.path,'b'*64)
        self.assertNotEqual(first,second)
        self.assertEqual(second,identidade.load_identity(self.path,'b'*64))

    def test_concurrent_identity_creation_is_atomic(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids=list(pool.map(lambda _:identidade.load_identity(self.path,'a'*64),range(8)))
        self.assertEqual(len(set(ids)),1)

    def test_temporary_fallback_does_not_rotate_or_replace_hardware_reference(self):
        import sqlite3
        first=identidade.load_identity(self.path,'a'*64,'smbios')
        self.assertEqual(first,identidade.load_identity(self.path,'b'*64,'windows'))
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('SELECT hardware_key,key_kind FROM identity').fetchone(),('a'*64,'smbios'))
        self.assertEqual(first,identidade.load_identity(self.path,'a'*64,'smbios'))

    def test_generic_serials_are_not_treated_as_serial_numbers(self):
        for value in ('To Be Filled By O.E.M.','Default string','Unknown','0'):
            self.assertEqual(identidade.clean_serial(value),'')
        self.assertEqual(identidade.clean_serial('ABC-123'),'ABC-123')

    def test_shared_read_only_identity_is_reused_but_not_on_different_hardware(self):
        first=identidade.load_identity(self.path,'a'*64,'smbios')
        self.assertEqual(identidade.read_only_identity(self.path,'a'*64,'smbios'),first)
        self.assertEqual(identidade.read_only_identity(self.path,'b'*64,'windows'),first)
        with self.assertRaises(PermissionError):
            identidade.read_only_identity(self.path,'b'*64,'smbios')

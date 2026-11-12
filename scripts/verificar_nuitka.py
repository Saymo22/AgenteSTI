"""Testa coleta/configuração em cópias temporárias, sem conectar à rede nem registrar startup."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sti.comum.versao import AGENT_VERSION


def check_agent(mode, base, work):
    source = base/'agente'/mode
    target = work/mode
    if mode == 'standalone':
        shutil.copytree(source/'agente.dist', target)
    else:
        target.mkdir()
        shutil.copyfile(source/'STI_Agente.exe', target/'STI_Agente.exe')
    config = {'STI_SERVER_IP': '127.0.0.77', 'STI_SERVER_PORT': 51259,
              'STI_AGENT_TOKEN': 'poc-local-only-not-a-real-token',
              'STI_IDENTITY_FILE': str(work/mode/'identity.db'), 'STI_ALLOW_POWER_COMMANDS': False}
    (target/'sti-config.json').write_text(json.dumps(config), encoding='utf-8')
    env = {key:value for key,value in os.environ.items() if not key.startswith('STI_')}
    env.update(LOCALAPPDATA=str(work/'Profile'), PROGRAMDATA=str(work/'ProgramData'))
    samples = []
    for attempt in range(2):
        result = subprocess.run([str(target/'STI_Agente.exe'), '--check'], cwd=ROOT/'tests', env=env,
                                capture_output=True, encoding='utf-8', errors='replace', timeout=60)
        (work/(mode+'-'+str(attempt)+'.stdout.log')).write_text(result.stdout, encoding='utf-8')
        (work/(mode+'-'+str(attempt)+'.stderr.log')).write_text(result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError('Diagnóstico do agente falhou em '+mode+'. Consulte os logs em '+str(work))
        start = result.stdout.find('{')
        if start < 0:
            raise RuntimeError('O diagnóstico não produziu JSON em '+mode+'. Consulte '+str(work))
        payload, _ = json.JSONDecoder().raw_decode(result.stdout[start:])
        if payload['agent_version'] != AGENT_VERSION or not payload['os'].startswith('Windows'):
            raise RuntimeError('Versão ou sistema inesperado em '+mode)
        if payload.get('update_supported') or 'shutdown' in payload['capabilities']:
            raise RuntimeError('Execução portátil ativou capacidades não esperadas.')
        if not isinstance(payload.get('printers'), list):
            raise RuntimeError('Coleta de impressoras não retornou uma lista.')
        samples.append(payload)
    if samples[0]['agent_id'] != samples[1]['agent_id']:
        raise RuntimeError('A identidade mudou ao executar novamente em '+mode)
    return {'mode': mode, 'external_config': True, 'different_cwd': True, 'telemetry': True,
            'persistent_identity': True, 'printers': True, 'portable_update_disabled': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['standalone', 'onefile', 'both'], default='standalone')
    args = parser.parse_args()
    base = ROOT/'dist/compatibilidade/nuitka'/AGENT_VERSION
    work = ROOT/'.test-tmp'/('nuitka-check-'+uuid.uuid4().hex)
    work.mkdir(parents=True)
    outcomes = []
    for mode in (['standalone', 'onefile'] if args.mode == 'both' else [args.mode]):
        outcomes.append(check_agent(mode, base, work))
        print(mode+': configuração externa, coleta e identidade persistente OK.', flush=True)
    report = {'experimental': True, 'version': AGENT_VERSION, 'checks': outcomes,
              'network_contact': False, 'startup_registered': False, 'kaspersky_tested': False,
              'local_logs': str(work)}
    (base/'compatibility-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Relatório: '+str(base/'compatibility-check.json'))


if __name__ == '__main__':
    main()

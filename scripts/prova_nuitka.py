"""Build experimental isolado; não cria release STI nem altera o build de produção."""
import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sti.comum.releases import file_hash
from sti.comum.versao import AGENT_VERSION


def compiler_command(component, mode, output, compiler, jobs, payload=None):
    entry = ROOT / ('agente.py' if component == 'agente' else 'packaging/instalador.py')
    filename = 'STI_Agente.exe' if component == 'agente' else 'STI_Agente_Setup.exe'
    command = [sys.executable, '-m', 'nuitka', '--mode=' + mode, '--update-check=never',
               '--' + ('mingw64' if compiler == 'mingw64' else 'msvc=latest'),
               '--assume-yes-for-downloads', '--jobs=' + str(jobs), '--lto=no',
               '--windows-console-mode=force', '--output-filename=' + filename,
               '--output-dir=' + str(output), '--report=' + str(output/'compilation-report.xml'),
               '--include-data-files=' + str(ROOT/'sti/comum/release-public-key.pem') + '=sti/comum/release-public-key.pem',
               '--include-module=win32print', '--include-module=win32ts']
    if component == 'instalador':
        if payload is None or not payload.is_file():
            raise ValueError('Compile primeiro o agente em --mode onefile; o instalador atual distribui um único executável.')
        resources = ROOT/'build/nuitka-poc/resources'
        resources.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(payload, resources/'STI_Agente.exe')
        (resources/'setup-info.json').write_text(json.dumps({'version': AGENT_VERSION,
            'agent': {'sha256': file_hash(payload), 'size': payload.stat().st_size}}), encoding='utf-8')
        # Executáveis são binários no Nuitka; inclua o payload como executável, não como dado disfarçado.
        config = ROOT/'build/nuitka-poc/installer.nuitka-package.config.yml'
        config.write_text(json.dumps([{'module-name': 'sti.agente.instalacao', 'dlls': [{
            'from_filenames': {'relative_path': resources.as_posix(), 'prefixes': ['STI_Agente'],
                               'suffixes': ['exe'], 'executable': 'yes'}, 'dest_path': 'resources'}]}]), encoding='utf-8')
        command += ['--enable-plugin=tk-inter', '--user-package-configuration-file=' + str(config),
                    '--include-data-files=' + str(resources/'setup-info.json') + '=resources/setup-info.json']
    command.append(str(entry))
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', choices=['agente', 'instalador', 'todos'], default='agente')
    parser.add_argument('--mode', choices=['standalone', 'onefile', 'both'], default='standalone')
    parser.add_argument('--compiler', choices=['mingw64', 'msvc'], default='mingw64')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or platform.architecture()[0] != '64bit':
        parser.error('A prova validada usa Windows e Python 3.12 de 64 bits.')
    if not 1 <= args.jobs <= 16:
        parser.error('Use entre 1 e 16 tarefas de compilação.')
    base = ROOT/'dist/compatibilidade/nuitka'/AGENT_VERSION
    base.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'NUITKA_CACHE_DIR': str(ROOT/'build/nuitka-cache'), 'NUITKA_UPDATE_CHECK': 'never'}
    components = ['agente', 'instalador'] if args.component == 'todos' else [args.component]
    modes = ['standalone', 'onefile'] if args.mode == 'both' else [args.mode]
    for component in components:
        for mode in modes:
            output = base/component/mode
            output.mkdir(parents=True, exist_ok=True)
            payload = base/'agente/onefile/STI_Agente.exe'
            command = compiler_command(component, mode, output, args.compiler, args.jobs, payload)
            started = time.monotonic()
            record = {'experimental': True, 'production_release': False, 'agent_version': AGENT_VERSION,
                      'nuitka': importlib.metadata.version('Nuitka'), 'python': platform.python_version(),
                      'compiler': args.compiler, 'component': component, 'mode': mode,
                      'command': command, 'status': 'compiling'}
            report = output/'build-info.json'
            report.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            print('Compilando ' + component + ' / ' + mode, flush=True)
            try:
                subprocess.run(command, cwd=ROOT, env=env, check=True)
            except BaseException:
                record['status'] = 'failed'
                raise
            else:
                record['status'] = 'compiled'
                print('Concluído: ' + str(output), flush=True)
            finally:
                record['seconds'] = round(time.monotonic()-started, 2)
                report.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Prova experimental. Nenhuma release de produção foi gerada.', flush=True)


if __name__ == '__main__':
    main()

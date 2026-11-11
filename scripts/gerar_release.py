"""Compila agente/instalador e produz a release assinada para o servidor STI."""
import argparse
import base64
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sti.comum.releases import canonical_json, file_hash, verify_manifest, version_tuple
from sti.comum.versao import AGENT_VERSION


def file_info(path):
    return {'sha256': file_hash(path), 'size': Path(path).stat().st_size}


def create_bundle(agent, installer, version, notes, private_key, destination):
    version_tuple(version)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    package = destination / 'agent.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(agent, 'STI_Agente.exe')
    manifest = {'format': 1, 'platform': 'windows-x64', 'version': version, 'notes': notes,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'agent': file_info(agent), 'package': file_info(package), 'installer': file_info(installer)}
    key = serialization.load_pem_private_key(Path(private_key).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Chave privada incompatível.')
    envelope = {'manifest': manifest, 'signature': base64.b64encode(key.sign(canonical_json(manifest))).decode('ascii')}
    verify_manifest(envelope)
    manifest_path = destination / 'manifest.json'
    manifest_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding='utf-8')
    bundle = destination / f'STI_Release_{version}.sti'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(package, 'agent.zip')
        archive.write(installer, 'installer.exe')
        archive.write(manifest_path, 'manifest.json')
    copied_installer = destination / f'STI_Agente_Setup_{version}.exe'
    shutil.copyfile(installer, copied_installer)
    return bundle, copied_installer, manifest_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--notes', default='Atualização do agente STI.')
    parser.add_argument('--notes-file', type=Path)
    parser.add_argument('--key', type=Path, default=ROOT / '.release-keys/agent-signing-key.pem')
    parser.add_argument('--bump', choices=['patch', 'minor', 'major'])
    parser.add_argument('--github-release', action='store_true')
    args = parser.parse_args()
    version = AGENT_VERSION
    if not args.key.is_file():
        raise SystemExit('A chave privada de publicação não foi encontrada. Preserve a chave original em .release-keys.')
    if args.bump:
        values = list(version_tuple(version))
        index = {'major': 0, 'minor': 1, 'patch': 2}[args.bump]
        values[index] += 1
        for position in range(index + 1, 3):
            values[position] = 0
        version = '.'.join(map(str, values))
        (ROOT / 'sti/comum/versao.py').write_text(f'AGENT_VERSION = "{version}"\n', encoding='utf-8')
    notes = args.notes_file.read_text(encoding='utf-8') if args.notes_file else args.notes
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', 'packaging/STI_Agente_V3_4.spec'], cwd=ROOT, check=True)
    resources = ROOT / 'build/release-resources'
    resources.mkdir(parents=True, exist_ok=True)
    (resources / 'setup-info.json').write_text(json.dumps({'version': version, 'agent': file_info(ROOT / 'dist/STI_Agente.exe')}), encoding='utf-8')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', 'packaging/STI_Agente_Setup.spec'], cwd=ROOT, check=True)
    artifacts = create_bundle(ROOT / 'dist/STI_Agente.exe', ROOT / 'dist/STI_Agente_Setup.exe', version,
                              notes, args.key, ROOT / 'dist/releases' / version)
    print('Release assinada gerada em ' + str(artifacts[0]))
    if args.github_release:
        notes_path = ROOT / 'build/release-notes.txt'
        notes_path.write_text(notes, encoding='utf-8')
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        subprocess.run(['gh', 'release', 'create', 'v' + version, *map(str, artifacts), '--target', commit,
                        '--title', 'STI Agente ' + version, '--notes-file', str(notes_path)], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()

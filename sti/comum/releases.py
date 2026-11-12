"""Formato assinado compartilhado pelo publicador, servidor e atualizador."""
import base64
import hashlib
import json
import re
import tempfile
import time
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PUBLIC_KEY_FILE = Path(__file__).with_name('release-public-key.pem')
MAX_BINARY = 100 * 1024 * 1024
MAX_PACKAGE = 120 * 1024 * 1024
MAX_BUNDLE = 220 * 1024 * 1024
AGENT_FILENAME = 'STI_Agente.exe'


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})', value):
        raise ValueError('Use uma versão no formato 3.4.0.')
    return tuple(map(int, value.split('.')))


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(envelope, public_key_file=None):
    try:
        manifest = envelope['manifest']
        if not isinstance(manifest, dict) or manifest.get('format') not in (1, 2) or manifest.get('platform') != 'windows-x64':
            raise ValueError('Formato de release incompatível.')
        version_tuple(manifest['version'])
        if manifest['format'] == 2 and manifest.get('package') != manifest.get('installer'):
            raise ValueError('A atualização MSI deve usar o próprio instalador.')
        for name, maximum in (('agent', MAX_BINARY), ('package', MAX_PACKAGE), ('installer', MAX_BINARY)):
            info = manifest[name]
            if (not isinstance(info, dict) or not isinstance(info.get('size'), int)
                    or isinstance(info['size'], bool) or not 0 < info['size'] <= maximum
                    or not isinstance(info.get('sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', info['sha256'])):
                raise ValueError('Tamanho ou hash inválido na release.')
        if not isinstance(manifest.get('notes', ''), str) or len(manifest.get('notes', '')) > 10000:
            raise ValueError('Notas da release inválidas.')
        key = serialization.load_pem_public_key(Path(public_key_file or PUBLIC_KEY_FILE).read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError('Chave pública incompatível.')
        key.verify(base64.b64decode(envelope['signature'], validate=True), canonical_json(manifest))
    except (KeyError, TypeError, InvalidSignature, ValueError) as error:
        raise ValueError('Release inválida ou assinatura não reconhecida.') from error
    return manifest


def verify_file(path, info):
    path = Path(path)
    if path.stat().st_size != info['size'] or file_hash(path) != info['sha256']:
        raise ValueError('O arquivo recebido não corresponde à release assinada.')


def copy_limited(source, destination, maximum):
    size = 0
    with Path(destination).open('wb') as output:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            size += len(chunk)
            if size > maximum:
                raise ValueError('Arquivo excede o tamanho permitido.')
            output.write(chunk)
    return size


def unpack_agent(package, destination, manifest):
    verify_file(package, manifest['package'])
    with zipfile.ZipFile(package) as archive:
        if archive.namelist() != [AGENT_FILENAME]:
            raise ValueError('O pacote deve conter somente o executável do agente.')
        member = archive.getinfo(AGENT_FILENAME)
        if member.file_size != manifest['agent']['size'] or member.flag_bits & 1:
            raise ValueError('Executável inválido no pacote.')
        with archive.open(member) as source:
            copy_limited(source, destination, MAX_BINARY)
    verify_file(destination, manifest['agent'])


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
        deadline = time.monotonic() + 3
        while True:
            try:
                temporary.replace(path)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.05)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_json(path, default=None):
    try:
        with Path(path).open(encoding='utf-8-sig') as stream:
            return json.load(stream)
    except FileNotFoundError:
        return default

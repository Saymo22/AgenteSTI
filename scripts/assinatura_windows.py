"""Assinatura de executáveis com certificado existente e SignTool do Windows SDK."""
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def signing_options(thumbprint, timestamp_url, tool=None):
    if not thumbprint:
        if timestamp_url or tool:
            raise ValueError('Informe --sign-cert para usar as opções de assinatura Windows.')
        return None
    if sys.platform != 'win32':
        raise ValueError('A assinatura Authenticode exige Windows.')
    normalized = str(thumbprint).replace(' ', '').upper()
    if not re.fullmatch(r'[0-9A-F]{40}', normalized):
        raise ValueError('Informe o thumbprint de 40 caracteres do certificado de assinatura de código.')
    parsed = urlparse(timestamp_url or '')
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Informe --timestamp-url com o servidor de carimbo de tempo do seu emissor.')
    executable = Path(tool or shutil.which('signtool.exe') or '')
    if not executable.is_file():
        raise ValueError('SignTool não encontrado. Informe --signtool com o executável do Windows SDK.')
    return {'tool': str(executable.resolve()), 'thumbprint': normalized, 'timestamp_url': timestamp_url}


def sign_and_verify(path, options):
    if not options:
        return
    executable = Path(path).resolve()
    if not executable.is_file():
        raise ValueError('O executável a assinar não foi encontrado.')
    subprocess.run([options['tool'], 'sign', '/sha1', options['thumbprint'], '/fd', 'SHA256',
                    '/tr', options['timestamp_url'], '/td', 'SHA256', str(executable)],
                   check=True, timeout=180)
    # Uma assinatura que não passa pela política Authenticode interrompe o build.
    subprocess.run([options['tool'], 'verify', '/pa', '/all', str(executable)],
                   check=True, timeout=180)

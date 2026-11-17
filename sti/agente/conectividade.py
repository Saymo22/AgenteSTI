"""Testes leves em segundo plano; não envia credenciais STI a sites externos."""
import logging
import platform
import subprocess
import threading
import time

import requests

INTERVAL = 60
PROBE_URL = 'http://www.msftconnecttest.com/connecttest.txt'
EXPECTED_BODY = b'Microsoft Connect Test'


def ping_external():
    windows = platform.system() == 'Windows'
    command = ['ping', '-n', '1', '-w', '2000', '8.8.8.8'] if windows else ['ping', '-c', '1', '-W', '2', '8.8.8.8']
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=3, creationflags=subprocess.CREATE_NO_WINDOW if windows else 0)
        # No Windows, uma resposta "destino inacessível" também pode retornar código zero.
        return result.returncode == 0 and (not windows or b'ttl=' in result.stdout.lower())
    except subprocess.TimeoutExpired:
        return False
    except OSError:
        return None


def http_external():
    try:
        with requests.get(PROBE_URL, timeout=(3, 3), allow_redirects=False, stream=True,
                          headers={'User-Agent': 'STI-Connectivity-Check'}) as response:
            if response.status_code != 200:
                return False
            body = next(response.iter_content(chunk_size=128), b'')
            return body.strip() == EXPECTED_BODY
    except requests.RequestException:
        return False


def probe():
    ping, http = ping_external(), http_external()
    status = 'available' if http else 'limited' if ping else 'unavailable' if ping is False else 'unknown'
    return {'status': status, 'ping': ping, 'http': http}


class InternetMonitor:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._sample = {'status': 'unknown', 'ping': None, 'http': None}
        self._checked = None

    def start(self):
        with self._lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name='STI-connectivity', daemon=True)
                self._thread.start()

    def report(self):
        with self._lock:
            age = None if self._checked is None else min(86400, max(0, time.monotonic() - self._checked))
            return {**self._sample, 'checked_ago_seconds': age}

    def _run(self):
        while True:
            try:
                sample = probe()
                with self._lock:
                    self._sample, self._checked = sample, time.monotonic()
            except Exception:
                logging.getLogger(__name__).exception('Falha no teste de conectividade.')
            time.sleep(INTERVAL)


monitor = InternetMonitor()

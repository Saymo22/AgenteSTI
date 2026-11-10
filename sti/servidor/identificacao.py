"""DNS reverso em segundo plano, sem atrasar a varredura de presença."""
import queue
import logging
import socket
import threading
import time


class HostnameResolver:
    def __init__(self, on_result, workers=2, ttl=900):
        self.on_result = on_result
        self.workers = workers
        self.ttl = ttl
        self.pending = queue.Queue(maxsize=128)
        self.lock = threading.Lock()
        self.retry_at = {}
        self.started = False

    def schedule(self, ip):
        with self.lock:
            now = time.monotonic()
            if self.retry_at.get(ip, 0) > now:
                return
            try:
                self.pending.put_nowait(ip)
            except queue.Full:
                return
            self.retry_at[ip] = float("inf")
            if not self.started:
                self.started = True
                for index in range(self.workers):
                    threading.Thread(target=self._worker, name=f"sti-dns-{index}", daemon=True).start()

    def _worker(self):
        while True:
            ip = self.pending.get()
            try:
                self.resolve(ip)
            except Exception:
                logging.getLogger("STI").exception("Falha ao atualizar identificação de %s", ip)
            finally:
                with self.lock:
                    self.retry_at[ip] = time.monotonic() + self.ttl
                self.pending.task_done()

    def resolve(self, ip):
        try:
            hostname = socket.gethostbyaddr(ip)[0].rstrip(".")
            if (hostname and hostname != ip and len(hostname) <= 253
                    and not any(char.isspace() or ord(char) < 32 for char in hostname)):
                self.on_result(ip, hostname)
        except (OSError, UnicodeError):
            pass  # Ausência de PTR é comum; o equipamento continua visível pelo IP.

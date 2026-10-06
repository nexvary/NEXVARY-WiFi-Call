"""Actual privileged isolation check; exclusively on a disposable CI runner."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
from socketserver import UnixStreamServer, StreamRequestHandler
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
from isolation_probe import probe


class Sentinel(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        payload = b'host-service-alive'
        self.send_response(200)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class UnixSentinel(StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        if self.rfile.readline(64) == b'NEXVARY-ISOLATION-PROBE\n':
            self.wfile.write(b'private-unix-bridge-alive')


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted' or os.geteuid() != 0:
        raise RuntimeError('Disposable GitHub-hosted root runner required.')
    release = Path('/etc/os-release').read_text()
    if 'ID=ubuntu' not in release or 'VERSION_ID="24.04"' not in release:
        raise RuntimeError('Ubuntu 24.04 runner required.')
    # An occupied port refuses this test; an existing host service is never stopped.
    server = ThreadingHTTPServer(('127.0.0.1', 8787), Sentinel)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with urlopen('http://127.0.0.1:8787/', timeout=3) as response:
            if response.read() != b'host-service-alive':
                raise RuntimeError('Host sentinel unavailable.')
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('isolation_probe.py')), '--probe'],
                                capture_output=True, timeout=30, check=False)
        if result.returncode:
            raise RuntimeError('Actual namespace probe failed; review runner support.')
        data = json.loads(result.stdout)
        if not data.get('host_state_unchanged') or not data.get('host_loopback_unreachable') or data.get('gateway_started'):
            raise RuntimeError('Incomplete isolation result.')
        with tempfile.TemporaryDirectory(prefix='nexvary-unix-isolation-') as directory:
            path = str(Path(directory) / 'proof.sock')
            channel = UnixStreamServer(path, UnixSentinel)
            os.chmod(path, 0o600)
            listener = threading.Thread(target=channel.serve_forever, daemon=True)
            listener.start()
            try:
                proof = probe(proof_socket=path)
                if not proof['host_state_unchanged']:
                    raise RuntimeError('Cross-namespace Unix proof failed.')
            finally:
                channel.shutdown(); channel.server_close(); listener.join(timeout=3)
        with urlopen('http://127.0.0.1:8787/', timeout=3) as response:
            if response.read() != b'host-service-alive':
                raise RuntimeError('Host sentinel was affected.')
        print('PASS: private network/mount/PID, resolver mutation and Unix transport across namespaces; host routes/rules/DNS and sentinel unchanged. No gateway or AKA executed.')
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=3)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Isolation smoke failed; no carrier success is established.') from None

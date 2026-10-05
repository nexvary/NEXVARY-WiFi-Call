#!/usr/bin/env python3
"""Local-only, authenticated host dashboard. No gateway execution or SIM secrets."""
import argparse
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STAGES = ['SIM', 'AKA', 'ePDG', 'IPsec', 'IMS', 'Outbound', 'Inbound', 'Audio']

def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

def snapshot():
    memory = {}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, value = line.split(':', 1)
            memory[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError):
        pass
    disk = os.statvfs('/')
    try:
        uptime = float(Path('/proc/uptime').read_text().split()[0])
    except (OSError, ValueError):
        uptime = None
    return dict(cpu_count=os.cpu_count(), load=os.getloadavg()[0],
                memory_total=memory.get('MemTotal'), memory_available=memory.get('MemAvailable'),
                swap_total=memory.get('SwapTotal'), swap_free=memory.get('SwapFree'),
                disk_total=disk.f_blocks * disk.f_frsize, disk_free=disk.f_bavail * disk.f_frsize,
                uptime=uptime, timestamp=time.time(), gateway_installed=False,
                stages=[dict(name=name, status='not_tested', evidence=None) for name in STAGES])

class PanelServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, state_dir):
        self.credentials = json.loads((Path(state_dir) / 'password.json').read_text())
        self.sessions = {}
        self.attempts = []
        self.lock = threading.Lock()
        super().__init__(address, Handler)

class Handler(BaseHTTPRequestHandler):
    server_version = 'NEXVARY'
    def setup(self):
        super().setup()
        self.connection.settimeout(10)
    def log_message(self, fmt, *args):
        pass  # Never log credentials, cookies or request payloads.
    def reply(self, status, body, content_type='application/json', cookie=None):
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)
    def permitted_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
    def session(self):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
            token = jar['session'].value
        except (KeyError, cookies.CookieError):
            return False
        with self.server.lock:
            now = time.time()
            self.server.sessions = {k: v for k, v in self.server.sessions.items() if v > now}
            return token in self.server.sessions
    def do_GET(self):
        if not self.permitted_host():
            return self.reply(403, {'error': 'host'})
        if self.path == '/':
            return self.reply(200, Path(__file__).with_name('index.html').read_bytes(), 'text/html; charset=utf-8')
        if self.path == '/healthz':
            return self.reply(200, {'panel': 'ok', 'gateway_verified': False})
        if self.path == '/api/status':
            if not self.session():
                return self.reply(401, {'error': 'login_required'})
            return self.reply(200, snapshot())
        self.reply(404, {'error': 'not_found'})
    def do_POST(self):
        if not self.permitted_host():
            return self.reply(403, {'error': 'host'})
        expected = f'http://{self.headers.get("Host")}'
        if self.headers.get('Origin') != expected:
            return self.reply(403, {'error': 'origin'})
        if self.path == '/api/logout':
            jar = cookies.SimpleCookie()
            try:
                jar.load(self.headers.get('Cookie', ''))
                with self.server.lock:
                    self.server.sessions.pop(jar['session'].value, None)
            except (KeyError, cookies.CookieError):
                pass
            return self.reply(200, {'ok': True}, cookie='session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
        if self.path != '/api/login':
            return self.reply(404, {'error': 'not_found'})
        with self.server.lock:
            now = time.time()
            self.server.attempts = [x for x in self.server.attempts if now - x < 60]
            if len(self.server.attempts) >= 5:
                return self.reply(429, {'error': 'try_later'})
            self.server.attempts.append(now)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2048 or self.headers.get('Content-Type') != 'application/json':
                return self.reply(400, {'error': 'invalid_request'})
            password = json.loads(self.rfile.read(length))['password']
            if not isinstance(password, str) or len(password) > 512:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            return self.reply(400, {'error': 'invalid_request'})
        creds = self.server.credentials
        if not hmac.compare_digest(password_hash(password, creds['salt']), creds['hash']):
            return self.reply(401, {'error': 'invalid_password'})
        token = secrets.token_urlsafe(32)
        with self.server.lock:
            if len(self.server.sessions) >= 100:
                self.server.sessions.clear()
            self.server.sessions[token] = time.time() + 3600
        self.reply(200, {'ok': True}, cookie=f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--init-password', action='store_true')
    args = parser.parse_args()
    if args.init_password:
        password = getpass.getpass('Admin password (at least 12 characters): ')
        if len(password) < 12 or password != getpass.getpass('Confirm password: '):
            raise SystemExit('Password must match and contain at least 12 characters.')
        directory = Path(args.state_dir)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        salt = secrets.token_hex(16)
        target = directory / 'password.json'
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(dict(salt=salt, hash=password_hash(password, salt)), stream)
        return
    PanelServer(('127.0.0.1', args.port), args.state_dir).serve_forever()

if __name__ == '__main__':
    main()

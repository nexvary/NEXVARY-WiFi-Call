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
import stat
import threading
import time
import uuid
from urllib.parse import urlsplit
from phone_store import PhoneStore
from aka_broker import AkaBroker
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
    def __init__(self, address, state_dir, public_origin=None):
        self.credentials = json.loads((Path(state_dir) / 'password.json').read_text())
        if public_origin:
            parsed = urlsplit(public_origin)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                raise ValueError('Public origin must be an HTTPS origin without a path.')
        self.public_origin = public_origin
        self.phone_store = PhoneStore(state_dir)
        self.aka_broker = AkaBroker()
        self.engine_slots = threading.BoundedSemaphore(2)
        self.engine_token_hash = None
        token_path = Path(state_dir) / 'engine-token.sha256'
        try:
            fd = os.open(token_path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        except FileNotFoundError:
            pass  # Engine access is disabled until separately provisioned.
        else:
            with os.fdopen(fd, 'r') as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                        or info.st_uid != Path(state_dir).stat().st_uid):
                    raise ValueError('Engine credential file must be private and regular.')
                raw_digest = stream.read(67)
                digest = raw_digest.removesuffix('\n')
                if len(raw_digest) > 65 or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                    raise ValueError('Invalid engine credential digest.')
                self.engine_token_hash = digest
        self.phone_attempts = []
        self.sessions = {}
        self.attempts = []
        self.lock = threading.Lock()
        self.worker_slots = threading.BoundedSemaphore(16)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.worker_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.worker_slots.release()
            raise
    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.worker_slots.release()

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
        if self.path == '/assets/qrcodegen.js':
            # Fixed allowlisted filename: never resolve an arbitrary URL as a filesystem path.
            return self.reply(200, Path(__file__).with_name('qrcodegen.js').read_bytes(), 'text/javascript; charset=utf-8')
        if self.path == '/healthz':
            return self.reply(200, {'panel': 'ok', 'gateway_verified': False})
        if self.path == '/api/admin/devices':
            if not self.session():
                return self.reply(401, {'error': 'login_required'})
            return self.reply(200, {'devices': self.server.phone_store.list_devices()})
        if self.path == '/api/status':
            if not self.session():
                return self.reply(401, {'error': 'login_required'})
            return self.reply(200, snapshot())
        self.reply(404, {'error': 'not_found'})
    def read_json(self):
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 4096 or self.headers.get('Content-Type', '').split(';', 1)[0].strip() != 'application/json':
            raise ValueError('Invalid request.')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Duplicate field.')
                result[key] = value
            return result
        def invalid_constant(_):
            raise ValueError('Invalid JSON constant.')
        data = json.loads(self.rfile.read(length), object_pairs_hook=unique, parse_constant=invalid_constant)
        if not isinstance(data, dict):
            raise ValueError('Invalid request.')
        return data
    def phone_request(self):
        try:
            data = self.read_json()
            if self.path == '/api/phone/pair':
                with self.server.lock:
                    now = time.time()
                    self.server.phone_attempts = [x for x in self.server.phone_attempts if now - x < 60]
                    if len(self.server.phone_attempts) >= 20:
                        return self.reply(429, {'error': 'try_later'})
                    self.server.phone_attempts.append(now)
                if set(data) != {'code'}:
                    raise ValueError()
                return self.reply(200, self.server.phone_store.pair(data['code']))
            header = self.headers.get('Authorization', '')
            if not header.startswith('Bearer ') or len(header) > 256:
                raise PermissionError()
            token = header[7:]
            if self.path.startswith('/api/phone/aka/'):
                device_id = self.server.phone_store.authorize(token)
                broker = self.server.aka_broker
                if self.path == '/api/phone/aka/session' and set(data) == {'selected_slot'}:
                    return self.reply(200, broker.begin(device_id, data['selected_slot']))
                if self.path == '/api/phone/aka/poll' and set(data) == {'session_id'}:
                    return self.reply(200, {'challenge': broker.poll(device_id, data['session_id'])})
                if self.path == '/api/phone/aka/stop' and set(data) == {'session_id'}:
                    broker.stop(device_id, data['session_id'])
                    return self.reply(200, {'ok': True})
                if self.path == '/api/phone/aka/result' and set(data) == {'session_id', 'challenge_id', 'state', 'payload'}:
                    broker.submit(device_id, data['session_id'], {k: data[k] for k in ('challenge_id', 'state', 'payload')})
                    return self.reply(200, {'ok': True})
                raise ValueError()
            if self.path == '/api/phone/report':
                self.server.phone_store.report(token, data)
                return self.reply(200, {'ok': True})
            if self.path == '/api/phone/disconnect':
                if data:
                    raise ValueError()
                # Authenticate through the store without accepting an arbitrary device ID.
                device_id = self.server.phone_store.authorize(token)
                self.server.phone_store.disconnect(token)
                self.server.aka_broker.revoke(device_id)
                return self.reply(200, {'ok': True})
            self.reply(404, {'error': 'not_found'})
        except PermissionError:
            self.reply(401, {'error': 'unauthorized'})
        except (ValueError, TypeError, KeyError):
            self.reply(400, {'error': 'invalid_request'})
    def engine_request(self):
        if any(self.headers.get(name) is not None for name in ('Origin', 'Forwarded', 'X-Forwarded-Proto', 'X-Forwarded-For')):
            return self.reply(403, {'error': 'local_engine_only'})
        if self.server.engine_token_hash is None:
            return self.reply(503, {'error': 'engine_disabled'})
        header = self.headers.get('Authorization', '')
        token = header[7:] if header.startswith('Bearer ') else ''
        if not 32 <= len(token) <= 128 or not hmac.compare_digest(
                hashlib.sha256(token.encode()).hexdigest(), self.server.engine_token_hash):
            return self.reply(401, {'error': 'unauthorized'})
        try:
            data = self.read_json()
            if set(data) != {'device_id', 'rand', 'autn'}:
                raise ValueError()
            if not isinstance(data['device_id'], str) or str(uuid.UUID(data['device_id'])) != data['device_id']:
                raise ValueError()
            if not self.server.phone_store.contains_device(data['device_id']):
                return self.reply(401, {'error': 'unauthorized'})
            if not self.server.engine_slots.acquire(blocking=False):
                return self.reply(429, {'error': 'try_later'})
            try:
                result = self.server.aka_broker.request(data['device_id'], data['rand'], data['autn'])
                try:
                    if not self.server.phone_store.contains_device(data['device_id']):
                        return self.reply(200, {'state': 'REVOKED', 'payload': None})
                    return self.reply(200, result.to_dict())
                finally:
                    result.clear()
            finally:
                self.server.engine_slots.release()
        except PermissionError:
            self.reply(401, {'error': 'unauthorized'})
        except (ValueError, TypeError, KeyError):
            self.reply(400, {'error': 'invalid_request'})
    def do_POST(self):
        if not self.permitted_host():
            return self.reply(403, {'error': 'host'})
        if self.path == '/api/engine/aka':
            return self.engine_request()
        if self.path in ('/api/phone/pair', '/api/phone/report', '/api/phone/disconnect',
                         '/api/phone/aka/session', '/api/phone/aka/poll', '/api/phone/aka/result', '/api/phone/aka/stop'):
            return self.phone_request()
        expected = f'http://{self.headers.get("Host")}'
        if self.headers.get('Origin') not in {expected, self.server.public_origin} or not self.headers.get('Origin'):
            return self.reply(403, {'error': 'origin'})
        if self.path in ('/api/admin/pairing', '/api/admin/revoke'):
            if not self.session():
                return self.reply(401, {'error': 'login_required'})
            try:
                data = self.read_json()
                if self.path == '/api/admin/pairing' and not data:
                    return self.reply(200, self.server.phone_store.create_pairing())
                if self.path == '/api/admin/revoke' and set(data) == {'device_id'} and isinstance(data['device_id'], str):
                    revoked = self.server.phone_store.revoke(data['device_id'])
                    self.server.aka_broker.revoke(data['device_id'])
                    return self.reply(200, {'ok': revoked})
                raise ValueError()
            except (ValueError, TypeError, KeyError):
                return self.reply(400, {'error': 'invalid_request'})
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
            if not 0 < length <= 2048 or self.headers.get('Content-Type', '').split(';', 1)[0].strip() != 'application/json':
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
        self.reply(200, {'ok': True}, cookie=f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600' + ('; Secure' if self.server.public_origin else ''))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--init-password', action='store_true')
    parser.add_argument('--public-origin')
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
    PanelServer(('127.0.0.1', args.port), args.state_dir, args.public_origin).serve_forever()

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Opt-in private Unix HTTP relay to the fixed loopback AKA broker endpoint.

No service is installed. No proxy environment, redirects, request logging,
authentication-material persistence or carrier evidence is used. A namespace may
bind-mount only this socket; it must not receive the host network namespace.
Python cannot guarantee erasure of temporary interpreter copies.
"""
import argparse
import base64
import binascii
import http.client
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import stat
import struct
import threading
import uuid

ENDPOINT = '/api/engine/aka'
MAX_BODY = 1024
TIMEOUT = 35
TOKEN = re.compile(r'Bearer [A-Za-z0-9_-]{32,128}\Z', re.ASCII)
HEX = re.compile(r'[A-Fa-f0-9]{32}\Z', re.ASCII)
ERROR_STATES = frozenset({
    'CARRIER_PRIVILEGE_REQUIRED', 'PERMISSION_REQUIRED', 'NO_ACTIVE_SIM',
    'TELEPHONY_UNAVAILABLE', 'UNSUPPORTED', 'SIM_NOT_SELECTED',
    'AUTHENTICATION_FAILED', 'MALFORMED_RESPONSE', 'SUBSCRIPTION_CHANGED',
    'TIMEOUT', 'SESSION_EXPIRED', 'SESSION_STOPPED', 'REVOKED',
})
ALLOWED_HEADERS = frozenset({'host', 'authorization', 'content-type',
                            'content-length', 'connection', 'accept-encoding', 'accept'})


def _wipe(value):
    if isinstance(value, bytearray):
        for index in range(len(value)):
            value[index] = 0


def _json_unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('Invalid JSON shape.')
        result[name] = value
    return result


def _request(body):
    try:
        data = json.loads(body, object_pairs_hook=_json_unique)
        if not isinstance(data, dict) or set(data) != {'device_id', 'rand', 'autn'}:
            raise ValueError()
        identifier = data['device_id']
        if not isinstance(identifier, str) or str(uuid.UUID(identifier)) != identifier:
            raise ValueError()
        if any(not isinstance(data[key], str) or HEX.fullmatch(data[key]) is None for key in ('rand', 'autn')):
            raise ValueError()
        return data
    except (ValueError, TypeError, UnicodeError, KeyError):
        raise ValueError('Invalid AKA request.') from None


def _response(body):
    raw = None
    try:
        data = json.loads(body, object_pairs_hook=_json_unique)
        if not isinstance(data, dict) or set(data) != {'state', 'payload'}:
            raise ValueError()
        state, payload = data['state'], data['payload']
        if not isinstance(state, str):
            raise ValueError()
        if state in ERROR_STATES:
            if payload is not None:
                raise ValueError()
        elif state in {'SUCCESS', 'SYNC_FAILURE'}:
            if not isinstance(payload, str) or not 1 <= len(payload) <= 72:
                raise ValueError()
            raw = bytearray(base64.b64decode(payload, validate=True))
            if base64.b64encode(raw).decode('ascii') != payload:
                raise ValueError()
            if state == 'SYNC_FAILURE':
                valid = len(raw) == 16 and raw[0] == 0xDC and raw[1] == 14
            else:
                valid = 40 <= len(raw) <= 52 and raw[0] == 0xDB and 4 <= raw[1] <= 16
                if valid:
                    offset = 2 + raw[1]
                    valid = raw[offset] == 16
                    offset += 17
                    valid = valid and offset < len(raw) and raw[offset] == 16
                    offset += 17
                    valid = valid and offset == len(raw)
            if not valid:
                raise ValueError()
        else:
            raise ValueError()
        return data
    except (ValueError, TypeError, UnicodeError, KeyError, IndexError, binascii.Error):
        raise ValueError('Invalid AKA response.') from None
    finally:
        _wipe(raw)


def _socket_directory(value):
    supplied = os.fspath(value)
    if not isinstance(supplied, str) or any(part in {'.', '..'} for part in supplied.split('/')):
        raise ValueError('Invalid socket path.')
    path = Path(supplied)
    if str(path) != supplied:
        raise ValueError('Invalid socket path.')
    if not path.is_absolute() or len(os.fsencode(path)) > 100 or not path.name:
        raise ValueError('Invalid socket path.')
    # Reject symlink components, including an existing socket. Never resolve them.
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ValueError('Symlink paths are forbidden.')
        except FileNotFoundError:
            pass
    directory = path.parent
    if not directory.exists():
        directory.mkdir(mode=0o700)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('Socket directory must be private and owned by the current UID.')
    try:
        path.lstat()
    except FileNotFoundError:
        return path
    raise ValueError('Refusing to replace an existing socket path.')


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, format, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.reply(code, {'error': 'invalid_request'})

    def reply(self, code, payload):
        body = bytearray(json.dumps(payload, separators=(',', ':')).encode('ascii'))
        try:
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)
        finally:
            _wipe(body)
            self.close_connection = True

    def do_POST(self):
        if self.path != ENDPOINT:
            return self.reply(404, {'error': 'unsupported_route'})
        names = [name.lower() for name in self.headers.keys()]
        if any(name not in ALLOWED_HEADERS for name in names) or len(names) != len(set(names)):
            return self.reply(400, {'error': 'invalid_headers'})
        if sum(len(name) + len(value) for name, value in self.headers.items()) > 2048:
            return self.reply(400, {'error': 'invalid_headers'})
        if TOKEN.fullmatch(self.headers.get('Authorization', '')) is None:
            return self.reply(401, {'error': 'unauthorized'})
        if self.headers.get('Content-Type', '').lower() not in {'application/json', 'application/json; charset=utf-8'}:
            return self.reply(415, {'error': 'invalid_content_type'})
        length_text = self.headers.get('Content-Length', '')
        if not re.fullmatch(r'[0-9]{1,4}', length_text):
            return self.reply(400, {'error': 'invalid_length'})
        length = int(length_text)
        if not 1 <= length <= MAX_BODY:
            return self.reply(413, {'error': 'request_too_large'})
        raw = bytearray()
        connection = None
        try:
            raw.extend(self.rfile.read(length))
            if len(raw) != length:
                return self.reply(400, {'error': 'invalid_request'})
            data = _request(raw)
            connection = http.client.HTTPConnection('127.0.0.1', 8787, timeout=TIMEOUT)
            connection.request('POST', ENDPOINT, json.dumps(data, separators=(',', ':')), headers={
                'Authorization': self.headers['Authorization'], 'Content-Type': 'application/json',
                'Accept': 'application/json',
            })
            response = connection.getresponse()
            body = bytearray(response.read(MAX_BODY + 1))
            try:
                if len(body) > MAX_BODY:
                    return self.reply(502, {'error': 'invalid_engine_response'})
                if response.status != 200:
                    code = response.status if response.status in {400, 401, 403, 429, 503} else 502
                    return self.reply(code, {'error': 'engine_rejected'})
                return self.reply(200, _response(body))
            finally:
                _wipe(body)
        except (OSError, http.client.HTTPException):
            self.reply(502, {'error': 'engine_unavailable'})
        except ValueError:
            self.reply(400 if connection is None else 502, {'error': 'invalid_request' if connection is None else 'invalid_engine_response'})
        finally:
            _wipe(raw)
            if connection is not None:
                connection.close()


class AkaUnixRelay(socketserver.UnixStreamServer):
    """Exactly two concurrent workers; no unbounded executor or waiting queue."""
    request_queue_size = 2

    def __init__(self, socket_path):
        if not hasattr(socket, 'SO_PEERCRED'):
            raise RuntimeError('Linux peer credentials are required.')
        self.path = _socket_directory(socket_path)
        self._workers = threading.BoundedSemaphore(2)
        self._threads = set()
        self._thread_lock = threading.Lock()
        self._identity = None
        super().__init__(str(self.path), _Handler, bind_and_activate=False)
        try:
            # Bind under a restrictive umask to avoid even a transient public socket.
            previous = os.umask(0o177)
            try:
                self.server_bind()
            finally:
                os.umask(previous)
            info = self.path.lstat()
            self._identity = (info.st_dev, info.st_ino, info.st_uid)
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError('Socket ownership/mode validation failed.')
            self.server_activate()
        except Exception:
            self.server_close()
            raise RuntimeError('Private socket creation failed.') from None

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(TIMEOUT)
        return connection, address

    def verify_request(self, request, client_address):
        try:
            _, uid, _ = struct.unpack('3i', request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            return uid == os.geteuid()
        except (OSError, ValueError, struct.error):
            return False

    def process_request(self, request, client_address):
        if not self._workers.acquire(blocking=False):
            try:
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json\r\nContent-Length: 22\r\nConnection: close\r\n\r\n{"error":"relay_busy"}')
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        def execute():
            try:
                self.finish_request(request, client_address)
            except Exception:
                # Never invoke BaseServer's stderr traceback with request context.
                pass
            finally:
                self.shutdown_request(request)
                self._workers.release()
                with self._thread_lock:
                    self._threads.discard(threading.current_thread())
        worker = threading.Thread(target=execute, daemon=True)
        with self._thread_lock:
            self._threads.add(worker)
        try:
            worker.start()
        except Exception:
            with self._thread_lock:
                self._threads.discard(worker)
            self._workers.release()
            self.shutdown_request(request)

    def handle_error(self, request, client_address):
        pass

    def server_close(self):
        super().server_close()
        if self._identity is not None:
            try:
                info = self.path.lstat()
                if stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino, info.st_uid) == self._identity:
                    self.path.unlink()
            except FileNotFoundError:
                pass
            self._identity = None

    def __repr__(self):
        return 'AkaUnixRelay(private, credentials=redacted)'


def main():
    parser = argparse.ArgumentParser(description='Opt-in private AKA Unix relay; no service installation.')
    parser.add_argument('--socket', required=True, help='Fresh socket in a current-UID directory with mode 0700.')
    options = parser.parse_args()
    relay = None
    try:
        relay = AkaUnixRelay(options.socket)
        relay.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit('AKA relay stopped; private endpoint validation failed.') from None
    finally:
        if relay is not None:
            relay.server_close()


if __name__ == '__main__':
    main()

"""Synthetic fixtures. Actual AF_UNIX -> fixed loopback HTTP checks require Linux."""
import base64
import contextlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import socket
import stat
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

from aka_unix_relay import AkaUnixRelay, ENDPOINT, _request, _response, _socket_directory

TOKEN = 't' * 43
DEVICE = 'd4119be3-74b6-43e7-b5e1-cf25e018db45'
REQUEST = {'device_id': DEVICE, 'rand': 'ab' * 16, 'autn': 'cd' * 16}
SUCCESS = base64.b64encode(bytes([0xDB, 4]) + b'R' * 4 + bytes([16]) + b'C' * 16 + bytes([16]) + b'I' * 16).decode()


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=3)
        self.path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        with self.server.condition:
            self.server.received.append((self.path, dict(self.headers), body))
            self.server.condition.notify_all()
        self.server.release.wait(timeout=2)
        authorized = self.headers.get('Authorization') == 'Bearer ' + TOKEN
        code = self.server.status if authorized else 401
        payload = self.server.response if authorized else {'error': 'unauthorized'}
        encoded = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        if code == 301:
            self.send_header('Location', 'http://example.invalid/private')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class RelayValidationTests(unittest.TestCase):
    def test_exact_request_fields_uuid_hex_and_duplicate_json_keys(self):
        self.assertEqual(REQUEST, _request(json.dumps(REQUEST).encode()))
        invalid = [dict(REQUEST, ki='forbidden'), dict(REQUEST, rand='ab'),
                   dict(REQUEST, autn='g' * 32), dict(REQUEST, device_id='not-a-uuid')]
        for data in invalid:
            with self.assertRaisesRegex(ValueError, '^Invalid AKA request.$'):
                _request(json.dumps(data).encode())
        with self.assertRaises(ValueError):
            _request(b'{"device_id":"one","device_id":"two","rand":"x","autn":"y"}')

    def test_response_accepts_db_dc_errors_but_no_forged_or_additional_evidence(self):
        for state, payload in [('SUCCESS', SUCCESS), ('SYNC_FAILURE', base64.b64encode(bytes([0xDC,14])+b'A'*14).decode()),
                               ('CARRIER_PRIVILEGE_REQUIRED', None), ('REVOKED', None)]:
            value = {'state': state, 'payload': payload}
            self.assertEqual(value, _response(json.dumps(value).encode()))
        for value in [{'state':'AKA_VERIFIED','payload':None}, {'state':'SUCCESS','payload':SUCCESS+'\n'},
                      {'state':'SUCCESS','payload':base64.b64encode(base64.b64decode(SUCCESS)+b'x').decode()},
                      {'state':'SUCCESS','payload':SUCCESS,'ki':'forbidden'},
                      {'state':'TIMEOUT','payload':SUCCESS}]:
            with self.assertRaisesRegex(ValueError, '^Invalid AKA response.$'):
                _response(json.dumps(value).encode())

    def test_directory_policy_rejects_public_mode_symlinks_and_existing_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _socket_directory(root/'fresh.sock')
            public = root/'public'; public.mkdir(mode=0o755)
            with self.assertRaises(ValueError):
                _socket_directory(public/'relay.sock')
            (root/'link').symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                _socket_directory(root/'link'/'relay.sock')
            existing = root/'existing.sock'; existing.write_text('preserve')
            with self.assertRaises(ValueError):
                _socket_directory(existing)
            self.assertEqual('preserve', existing.read_text())
            with self.assertRaises(ValueError):
                _socket_directory(Path('relative.sock'))
            for supplied in (str(root)+'/./relay.sock', str(root)+'/../relay.sock', str(root)+'//relay.sock'):
                with self.assertRaises(ValueError):
                    _socket_directory(supplied)

    def test_peer_uid_validation_and_redacted_repr(self):
        relay = object.__new__(AkaUnixRelay)
        peer = Mock()
        peer.getsockopt.return_value = struct.pack('3i', 42, os.geteuid(), os.getegid())
        self.assertTrue(relay.verify_request(peer, None))
        peer.getsockopt.return_value = struct.pack('3i', 42, os.geteuid()+1, os.getegid())
        self.assertFalse(relay.verify_request(peer, None))
        peer.getsockopt.side_effect = OSError()
        self.assertFalse(relay.verify_request(peer, None))
        self.assertNotIn(TOKEN, repr(relay))


class ActualUnixRelayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)/'relay.sock'
        # Fixed port is intentional: arbitrary relay destinations are forbidden.
        self.engine = ThreadingHTTPServer(('127.0.0.1',8787), FixtureHandler)
        self.engine.received = []
        self.engine.condition = threading.Condition()
        self.engine.release = threading.Event(); self.engine.release.set()
        self.engine.status = 200
        self.engine.response = {'state':'SUCCESS','payload':SUCCESS}
        self.engine.handle_error = lambda request,address: None
        self.engine_thread = threading.Thread(target=self.engine.serve_forever, kwargs={'poll_interval':.01}, daemon=True)
        self.engine_thread.start()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.close_engine)
        self.relay = AkaUnixRelay(self.path)
        self.relay_thread = threading.Thread(target=self.relay.serve_forever, kwargs={'poll_interval':.01}, daemon=True)
        self.relay_thread.start()
        self.addCleanup(self.close_relay)

    def close_relay(self):
        self.engine.release.set()
        self.relay.shutdown(); self.relay.server_close(); self.relay_thread.join(timeout=2)

    def close_engine(self):
        self.engine.release.set()
        self.engine.shutdown(); self.engine.server_close(); self.engine_thread.join(timeout=2)

    def request(self, method='POST', path=ENDPOINT, body=None, headers=None):
        connection = UnixConnection(self.path)
        try:
            supplied = {'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json','Accept':'application/json'}
            supplied.update(headers or {})
            connection.request(method, path, body=json.dumps(REQUEST) if body is None else body, headers=supplied)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_actual_unix_to_loopback_round_trip_no_logs_or_proxy_environment(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), contextlib.redirect_stdout(output):
            original = os.environ.get('HTTP_PROXY')
            os.environ['HTTP_PROXY'] = 'http://example.invalid:1'
            try:
                self.assertEqual((200,{'state':'SUCCESS','payload':SUCCESS}), self.request())
            finally:
                if original is None: os.environ.pop('HTTP_PROXY',None)
                else: os.environ['HTTP_PROXY'] = original
        self.assertEqual('', output.getvalue())
        path, headers, body = self.engine.received[0]
        self.assertEqual(ENDPOINT,path)
        self.assertEqual(REQUEST,json.loads(body))
        self.assertEqual('Bearer '+TOKEN,headers['Authorization'])
        self.assertNotIn('Origin',headers)
        self.assertNotIn('Forwarded',headers)
        self.assertEqual(0o600,stat.S_IMODE(self.path.lstat().st_mode))
        self.assertEqual(os.geteuid(),self.path.lstat().st_uid)

    def test_bad_bearer_and_unknown_routes_never_receive_authentication_data(self):
        self.assertEqual(401,self.request(headers={'Authorization':'Bearer short'})[0])
        self.assertEqual(404,self.request(path='/api/status')[0])
        self.assertEqual(501,self.request(method='GET')[0])
        self.assertEqual([],self.engine.received)
        self.assertEqual(401,self.request(headers={'Authorization':'Bearer '+'z'*43})[0])

    def test_disallowed_headers_oversize_and_wrong_json_are_not_forwarded(self):
        for name in ('Origin','Forwarded','X-Forwarded-For','X-Forwarded-Proto','Transfer-Encoding'):
            self.assertEqual(400,self.request(headers={name:'forbidden'})[0])
        self.assertEqual(413,self.request(body=b'x'*1025)[0])
        self.assertEqual(400,self.request(body=json.dumps(dict(REQUEST,ki='forbidden')))[0])
        self.assertEqual([],self.engine.received)

    def test_upstream_redirect_oversize_and_forged_results_fail_closed(self):
        self.engine.status = 301
        self.assertEqual((502,{'error':'engine_rejected'}),self.request())
        self.engine.status = 200
        self.engine.response = {'state':'SUCCESS','payload':SUCCESS,'ki':'forbidden'}
        self.assertEqual((502,{'error':'invalid_engine_response'}),self.request())
        self.engine.response = b'x'*1025
        self.assertEqual((502,{'error':'invalid_engine_response'}),self.request())

    def test_two_worker_bound_returns_busy_without_forwarding_third_request(self):
        self.engine.release.clear()
        outcomes = []
        workers = [threading.Thread(target=lambda:outcomes.append(self.request()),daemon=True) for _ in range(2)]
        for worker in workers: worker.start()
        with self.engine.condition:
            self.assertTrue(self.engine.condition.wait_for(lambda:len(self.engine.received)==2,timeout=2))
        self.assertEqual((503,{'error':'relay_busy'}),self.request())
        self.assertEqual(2,len(self.engine.received))
        self.engine.release.set()
        for worker in workers: worker.join(timeout=2)
        self.assertEqual(2,len(outcomes))
        self.assertTrue(all(result[0]==200 for result in outcomes))

    def test_cleanup_only_unlinks_owned_socket_inode_and_preserves_replacement(self):
        with self.assertRaises(ValueError):
            AkaUnixRelay(self.path)
        moved = self.path.with_name('original.sock')
        self.path.rename(moved)
        self.path.write_text('preserve replacement')
        self.relay.server_close()
        self.assertEqual('preserve replacement',self.path.read_text())
        self.assertTrue(moved.exists())

    def test_cleanup_unlinks_unchanged_owned_socket(self):
        self.relay.server_close()
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()

"""Exercise HTTP authentication and evidence boundaries on a temporary loopback panel."""
import http.client
from http.cookies import SimpleCookie
import json
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unittest

from app import PanelServer, STAGES, password_hash


class PanelHTTPTests(unittest.TestCase):
    password = 'temporary-unit-test-password'

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        salt = secrets.token_hex(16)
        credentials = dict(salt=salt, hash=password_hash(self.password, salt))
        Path(self.directory.name, 'password.json').write_text(json.dumps(credentials))
        self.server = PanelServer(('127.0.0.1', 0), self.directory.name)
        self.host = f'127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def request(self, method, path, body=None, headers=None):
        headers = {'Host': self.host, **(headers or {})}
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            connection.close()

    def login(self, password=None, headers=None):
        return self.request('POST', '/api/login', json.dumps({'password': self.password if password is None else password}),
                            {'Origin': f'http://{self.host}', 'Content-Type': 'application/json', **(headers or {})})

    def authenticated_cookie(self):
        status, headers, body = self.login()
        self.assertEqual(200, status)
        self.assertEqual({'ok': True}, body)
        jar = SimpleCookie(headers['Set-Cookie'])
        self.assertTrue(jar['session']['httponly'])
        self.assertEqual('Strict', jar['session']['samesite'])
        self.assertEqual('/', jar['session']['path'])
        self.assertEqual('3600', jar['session']['max-age'])
        self.assertGreaterEqual(len(jar['session'].value), 40)
        return f"session={jar['session'].value}"

    def test_status_requires_valid_authenticated_session(self):
        for headers in ({}, {'Cookie': 'session=forged-token'}, {'Cookie': 'invalid cookie'}):
            with self.subTest(headers=headers):
                status, _, body = self.request('GET', '/api/status', headers=headers)
                self.assertEqual(401, status)
                self.assertEqual({'error': 'login_required'}, body)
        cookie = self.authenticated_cookie()
        status, headers, body = self.request('GET', '/api/status', headers={'Cookie': cookie})
        self.assertEqual(200, status)
        self.assertEqual('no-store', headers['Cache-Control'])
        self.assertEqual('nosniff', headers['X-Content-Type-Options'])
        self.assertEqual('DENY', headers['X-Frame-Options'])
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertGreater(body['disk_total'], 0)

    def test_wrong_password_never_creates_session_and_hash_credentials_accept_correct_password(self):
        self.assertNotIn('password', self.server.credentials)
        self.assertNotEqual(self.password, self.server.credentials['hash'])
        status, headers, body = self.login('incorrect-password')
        self.assertEqual(401, status)
        self.assertEqual({'error': 'invalid_password'}, body)
        self.assertNotIn('Set-Cookie', headers)
        self.assertEqual({}, self.server.sessions)
        self.authenticated_cookie()
        self.assertEqual(1, len(self.server.sessions))

    def test_host_filter_rejects_rebinding_and_remote_hostnames(self):
        for host in ('attacker.example', f'attacker.example:{self.server.server_port}', '127.0.0.1:1'):
            with self.subTest(host=host):
                status, _, body = self.request('GET', '/healthz', headers={'Host': host})
                self.assertEqual((403, {'error': 'host'}), (status, body))
                status, _, body = self.login(headers={'Host': host, 'Origin': f'http://{host}'})
                self.assertEqual((403, {'error': 'host'}), (status, body))
        self.assertEqual({}, self.server.sessions)

    def test_login_rejects_missing_cross_origin_and_different_port_origin(self):
        for origin in ('', 'https://attacker.example', 'http://127.0.0.1:1', f'https://{self.host}', 'null'):
            with self.subTest(origin=origin):
                status, _, body = self.login(headers={'Origin': origin})
                self.assertEqual((403, {'error': 'origin'}), (status, body))
        status, _, body = self.request('POST', '/api/login', '{}', {'Content-Type': 'application/json'})
        self.assertEqual((403, {'error': 'origin'}), (status, body))
        self.assertEqual([], self.server.attempts)
        self.assertEqual({}, self.server.sessions)

    def test_localhost_host_and_matching_origin_can_authenticate(self):
        host = f'localhost:{self.server.server_port}'
        status, _, body = self.login(headers={'Host': host, 'Origin': f'http://{host}'})
        self.assertEqual((200, {'ok': True}), (status, body))

    def test_expired_sessions_are_rejected_and_removed(self):
        cookie = self.authenticated_cookie()
        token = SimpleCookie(cookie)['session'].value
        with self.server.lock:
            self.server.sessions[token] = time.time() - 1
        status, _, body = self.request('GET', '/api/status', headers={'Cookie': cookie})
        self.assertEqual((401, {'error': 'login_required'}), (status, body))
        self.assertNotIn(token, self.server.sessions)

    def test_logout_requires_same_origin_and_invalidates_session(self):
        cookie = self.authenticated_cookie()
        status, _, _ = self.request('POST', '/api/logout', headers={'Cookie': cookie, 'Origin': 'https://attacker.example'})
        self.assertEqual(403, status)
        self.assertEqual(200, self.request('GET', '/api/status', headers={'Cookie': cookie})[0])
        status, headers, body = self.request('POST', '/api/logout', headers={'Cookie': cookie, 'Origin': f'http://{self.host}'})
        self.assertEqual((200, {'ok': True}), (status, body))
        self.assertEqual('0', SimpleCookie(headers['Set-Cookie'])['session']['max-age'])
        self.assertEqual(401, self.request('GET', '/api/status', headers={'Cookie': cookie})[0])

    def test_rate_limit_blocks_sixth_attempt_and_expired_window_reopens(self):
        for _ in range(5):
            self.assertEqual(401, self.login('wrong')[0])
        status, headers, body = self.login()
        self.assertEqual((429, {'error': 'try_later'}), (status, body))
        self.assertNotIn('Set-Cookie', headers)
        self.assertEqual({}, self.server.sessions)
        with self.server.lock:
            self.server.attempts = [time.time() - 61] * 5
        self.authenticated_cookie()
        self.assertEqual(1, len(self.server.attempts))

    def test_malformed_or_oversized_login_is_rejected(self):
        origin = f'http://{self.host}'
        for body in ('not-json', '{}', '{"password": null}', json.dumps({'password': 'x' * 513})):
            with self.subTest(body=body[:30]):
                status, _, result = self.request('POST', '/api/login', body, {'Origin': origin, 'Content-Type': 'application/json'})
                self.assertEqual((400, {'error': 'invalid_request'}), (status, result))
        self.assertEqual(400, self.login(headers={'Content-Type': 'text/plain'})[0])
        with self.server.lock:
            self.server.attempts.clear()
        status, _, body = self.request('POST', '/api/login', 'x' * 2049, {'Origin': origin, 'Content-Type': 'application/json'})
        self.assertEqual((400, {'error': 'invalid_request'}), (status, body))
        self.assertEqual({}, self.server.sessions)

    def test_health_and_status_do_not_claim_carrier_or_gateway_success(self):
        status, _, health = self.request('GET', '/healthz')
        self.assertEqual(200, status)
        self.assertIs(health['gateway_verified'], False)
        cookie = self.authenticated_cookie()
        status, _, body = self.request('GET', '/api/status', headers={'Cookie': cookie})
        self.assertEqual(200, status)
        self.assertIs(body['gateway_installed'], False)
        self.assertEqual(['SIM', 'AKA', 'ePDG', 'IPsec', 'IMS', 'Outbound', 'Inbound', 'Audio'], STAGES)
        self.assertEqual(STAGES, [stage['name'] for stage in body['stages']])
        for stage in body['stages']:
            self.assertEqual('not_tested', stage['status'])
            self.assertIsNone(stage['evidence'])
        self.assertNotIn('credentials', body)
        self.assertNotIn('sessions', body)


if __name__ == '__main__':
    unittest.main()

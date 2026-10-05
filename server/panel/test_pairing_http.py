"""Phone pairing, report privacy and revocation through the real HTTP handler.

The fixture contains status evidence only; a delivered report never verifies a
SIM authentication exchange, gateway connection, call or audio path.
"""
import http.client
from http.cookies import SimpleCookie
import json
from pathlib import Path
import secrets
import tempfile
import threading
import unittest

from app import PanelServer, STAGES, password_hash


REPORT = {
    'schema_version': 1,
    'sim_count': 2,
    'selected_slot': 1,
    'network': 'WIFI',
    'phone_as_sim': 'CARRIER_PRIVILEGE_REQUIRED',
    'app_version': '0.3.0-alpha02',
    'android_api': 35,
}


class PairingHTTPTests(unittest.TestCase):
    public_origin = None

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.password = secrets.token_urlsafe(24)
        salt = secrets.token_hex(16)
        Path(self.directory.name, 'password.json').write_text(json.dumps({
            'salt': salt, 'hash': password_hash(self.password, salt),
        }))
        self.server = PanelServer(('127.0.0.1', 0), self.directory.name,
                                  public_origin=self.public_origin)
        self.host = f'127.0.0.1:{self.server.server_port}'
        self.origin = self.public_origin or f'http://{self.host}'
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port,
                                                 timeout=3)
        request_headers = {'Host': self.host, **(headers or {})}
        if payload is not None:
            request_headers['Content-Type'] = 'application/json'
        try:
            connection.request(method, path,
                               body=json.dumps(payload) if payload is not None else None,
                               headers=request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            connection.close()

    def login(self):
        status, headers, body = self.request('POST', '/api/login',
                                             {'password': self.password},
                                             {'Origin': self.origin})
        self.assertEqual(200, status)
        self.assertEqual({'ok': True}, body)
        jar = SimpleCookie(headers['Set-Cookie'])
        self.assertTrue(bool(jar['session']['httponly']))
        self.assertEqual('Strict', jar['session']['samesite'])
        if self.public_origin:
            self.assertTrue(bool(jar['session']['secure']))
        return {'Cookie': f"session={jar['session'].value}", 'Origin': self.origin}

    def pair_phone(self, admin):
        status, _, pairing = self.request('POST', '/api/admin/pairing', {}, admin)
        self.assertEqual(200, status)
        self.assertEqual({'code', 'expires_at'}, set(pairing))
        self.assertTrue(isinstance(pairing['code'], str))
        status, _, phone = self.request('POST', '/api/phone/pair', {'code': pairing['code']})
        self.assertEqual(200, status)
        self.assertEqual({'device_id', 'token'}, set(phone))
        self.assertTrue(isinstance(phone['device_id'], str))
        self.assertTrue(isinstance(phone['token'], str))
        # Assertion arguments contain only boolean membership results, never a
        # generated pairing code, bearer token or admin session value.
        return phone, pairing

    def device_list(self, admin):
        status, _, body = self.request('GET', '/api/admin/devices', headers=admin)
        self.assertEqual(200, status)
        self.assertEqual({'devices'}, set(body))
        return body['devices']

    def test_report_round_trip_is_allowlisted_and_does_not_verify_gateway_stages(self):
        admin = self.login()
        phone, pairing = self.pair_phone(admin)
        authorization = {'Authorization': 'Bearer ' + phone['token']}
        status, _, body = self.request('POST', '/api/phone/report', REPORT, authorization)
        self.assertEqual((200, {'ok': True}), (status, body))
        devices = self.device_list(admin)
        self.assertEqual(1, len(devices))
        self.assertEqual({'device_id', 'last_seen', 'report'}, set(devices[0]))
        self.assertTrue(devices[0]['device_id'] == phone['device_id'])
        self.assertGreater(devices[0]['last_seen'], 0)
        self.assertEqual(REPORT, devices[0]['report'])
        serialized = json.dumps(devices)
        self.assertFalse(phone['token'] in serialized)
        self.assertFalse(pairing['code'] in serialized)
        for secret_key in ('token', 'token_hash', 'code', 'code_hash', 'Ki', 'imsi', 'icc_id'):
            self.assertFalse(f'"{secret_key}"' in serialized)
        status, _, snapshot = self.request('GET', '/api/status', headers=admin)
        self.assertEqual(200, status)
        self.assertIs(snapshot['gateway_installed'], False)
        self.assertEqual(STAGES, [stage['name'] for stage in snapshot['stages']])
        for stage in snapshot['stages']:
            self.assertEqual('not_tested', stage['status'])
            self.assertIsNone(stage['evidence'])

    def test_admin_revoke_invalidates_phone_token(self):
        admin = self.login()
        phone, _ = self.pair_phone(admin)
        auth = {'Authorization': 'Bearer ' + phone['token']}
        status, _, body = self.request('POST', '/api/admin/revoke',
                                       {'device_id': phone['device_id']}, admin)
        self.assertEqual((200, {'ok': True}), (status, body))
        self.assertEqual([], self.device_list(admin))
        status, _, body = self.request('POST', '/api/phone/report', REPORT, auth)
        self.assertEqual((401, {'error': 'unauthorized'}), (status, body))

    def test_phone_disconnect_revokes_only_authenticated_phone(self):
        admin = self.login()
        phone, _ = self.pair_phone(admin)
        other, _ = self.pair_phone(admin)
        auth = {'Authorization': 'Bearer ' + phone['token']}
        status, _, body = self.request('POST', '/api/phone/disconnect', {}, auth)
        self.assertEqual((200, {'ok': True}), (status, body))
        remaining = self.device_list(admin)
        self.assertEqual(1, len(remaining))
        self.assertTrue(remaining[0]['device_id'] == other['device_id'])
        self.assertEqual(401, self.request('POST', '/api/phone/report', REPORT, auth)[0])
        self.assertEqual(401, self.request('POST', '/api/phone/disconnect', {}, auth)[0])
        self.assertEqual(200, self.request('POST', '/api/phone/report', REPORT,
                                         {'Authorization': 'Bearer ' + other['token']})[0])

    def test_secret_and_unknown_fields_are_rejected_without_persisting(self):
        admin = self.login()
        phone, _ = self.pair_phone(admin)
        auth = {'Authorization': 'Bearer ' + phone['token']}
        for field in ('Ki', 'imsi', 'phone_number', 'extra'):
            with self.subTest(field=field):
                marker = 'forbidden-http-test-marker-' + field
                status, _, body = self.request('POST', '/api/phone/report',
                                               {**REPORT, field: marker}, auth)
                self.assertEqual((400, {'error': 'invalid_request'}), (status, body))
                self.assertIsNone(self.device_list(admin)[0]['report'])
                for path in Path(self.directory.name).glob('phones.sqlite3*'):
                    self.assertFalse(marker.encode() in path.read_bytes())
        self.assertEqual(200, self.request('POST', '/api/phone/report', REPORT, auth)[0])
        for invalid in ({}, {key: value for key, value in REPORT.items() if key != 'network'}):
            self.assertEqual(400, self.request('POST', '/api/phone/report', invalid, auth)[0])
        self.assertEqual(REPORT, self.device_list(admin)[0]['report'])

    def test_admin_pair_and_revoke_require_session_and_correct_origin(self):
        self.assertEqual(401, self.request('GET', '/api/admin/devices')[0])
        self.assertEqual(401, self.request('POST', '/api/admin/pairing', {},
                                         {'Origin': self.origin})[0])
        admin = self.login()
        phone, _ = self.pair_phone(admin)
        for path, payload in (('/api/admin/pairing', {}),
                              ('/api/admin/revoke', {'device_id': phone['device_id']})):
            for origin in ('https://attacker.example', 'null', ''):
                with self.subTest(path=path, origin=origin):
                    self.assertEqual(403, self.request('POST', path, payload,
                                                      {**admin, 'Origin': origin})[0])
        self.assertEqual(1, len(self.device_list(admin)))

    def test_pairing_is_single_use_and_mobile_routes_still_require_loopback_host(self):
        admin = self.login()
        phone, pairing = self.pair_phone(admin)
        self.assertEqual(401, self.request('POST', '/api/phone/pair',
                                         {'code': pairing['code']})[0])
        auth = {'Authorization': 'Bearer ' + phone['token']}
        self.assertEqual(401, self.request('POST', '/api/phone/report', REPORT)[0])
        self.assertEqual(401, self.request('POST', '/api/phone/disconnect', {})[0])
        for path, payload in (('/api/phone/pair', {'code': pairing['code']}),
                              ('/api/phone/report', REPORT), ('/api/phone/disconnect', {})):
            self.assertEqual(403, self.request('POST', path, payload,
                                              {**auth, 'Host': 'panel.example.com'})[0])
        self.assertEqual(1, len(self.device_list(admin)))


class PublicOriginPairingHTTPTests(PairingHTTPTests):
    public_origin = 'https://panel.example.com'

    def test_proxy_public_origin_can_administer_with_secure_cookie(self):
        admin = self.login()
        for origin in ('https://other.example.com', 'http://panel.example.com',
                       'https://panel.example.com.evil.example', 'https://panel.example.com:444'):
            self.assertEqual(403, self.request('POST', '/api/admin/pairing', {},
                                              {**admin, 'Origin': origin})[0])
        phone, _ = self.pair_phone(admin)
        self.assertEqual(200, self.request('POST', '/api/phone/report', REPORT,
                                         {'Authorization': 'Bearer ' + phone['token']})[0])


if __name__ == '__main__':
    unittest.main()

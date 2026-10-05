"""Actual HTTP transport checks for the bounded Phone-as-SIM AKA broker.

All challenge bytes and DB payloads are synthetic fixtures. Transport success is
not evidence of an actual UICC computation, carrier authentication, IMS or calls.
"""
import base64
import hashlib
import http.client
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import queue
import secrets
import sys
import tempfile
import threading
import time
import unittest

from app import PanelServer, password_hash


SUCCESS_PAYLOAD = base64.b64encode(bytes([0xDB, 4]) + b'RESS' + bytes([16]) + b'C' * 16 + bytes([16]) + b'I' * 16).decode('ascii')


class AkaHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.password = secrets.token_urlsafe(24)
        self.engine_token = secrets.token_urlsafe(32)
        self.rand = secrets.token_hex(16)
        self.autn = secrets.token_hex(16)
        salt = secrets.token_hex(16)
        Path(self.directory.name, 'password.json').write_text(json.dumps({
            'salt': salt, 'hash': password_hash(self.password, salt),
        }))
        self.engine_file = Path(self.directory.name, 'engine-token.sha256')
        self.engine_file.write_text(hashlib.sha256(self.engine_token.encode('ascii')).hexdigest() + '\n')
        os.chmod(self.engine_file, 0o600)
        self.engine_jobs = []
        self.phone_sessions = []
        self.handler_errors = []
        self.start_server()

    def start_server(self):
        self.server = PanelServer(('127.0.0.1', 0), self.directory.name)
        # A response sent before a failing cleanup must not count as a green test.
        self.server.handle_error = lambda request, address: self.handler_errors.append(sys.exc_info()[0].__name__)
        self.host = f'127.0.0.1:{self.server.server_port}'
        self.origin = f'http://{self.host}'
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def tearDown(self):
        # Closing a fixture must not leave engine waiters active across test cases.
        for auth, session_id in self.phone_sessions:
            try:
                self.request('POST', '/api/phone/aka/stop', {'session_id': session_id}, auth)
            except (OSError, TimeoutError):
                pass
        for worker in self.engine_jobs:
            worker.join(timeout=3)
        self.close_server()
        self.directory.cleanup()
        self.assertEqual([], self.handler_errors, 'HTTP handler raised an exception after response/cleanup')

    def request(self, method, route, payload=None, headers=None, timeout=3):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=timeout)
        request_headers = {'Host': self.host, **(headers or {})}
        if payload is not None:
            request_headers['Content-Type'] = 'application/json'
        try:
            connection.request(method, route, body=json.dumps(payload) if payload is not None else None,
                               headers=request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            connection.close()

    def login(self):
        status, headers, _ = self.request('POST', '/api/login', {'password': self.password}, {'Origin': self.origin})
        self.assertEqual(200, status)
        token = SimpleCookie(headers['Set-Cookie'])['session'].value
        return {'Cookie': 'session=' + token, 'Origin': self.origin}

    def pair_phone(self, admin):
        status, _, body = self.request('POST', '/api/admin/pairing', {}, admin)
        self.assertEqual(200, status)
        status, _, phone = self.request('POST', '/api/phone/pair', {'code': body['code']})
        self.assertEqual(200, status)
        return phone, {'Authorization': 'Bearer ' + phone['token']}

    def begin(self, auth, slot=1):
        status, _, body = self.request('POST', '/api/phone/aka/session', {'selected_slot': slot}, auth)
        self.assertEqual(200, status)
        self.assertEqual(slot, body['selected_slot'])
        self.assertTrue(isinstance(body['session_id'], str) and bool(body['session_id']))
        self.assertGreater(body['expires_at'], 0)
        self.phone_sessions.append((auth, body['session_id']))
        return body['session_id']

    def begin_engine_request(self, device_id):
        completed = queue.Queue()
        def run():
            try:
                completed.put(self.request('POST', '/api/engine/aka',
                    {'device_id': device_id, 'rand': self.rand, 'autn': self.autn},
                    {'Authorization': 'Bearer ' + self.engine_token}, timeout=4))
            except Exception as error:
                completed.put(error)
        worker = threading.Thread(target=run, daemon=True)
        self.engine_jobs.append(worker)
        worker.start()
        return completed

    def await_challenge(self, auth, session_id):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status, _, body = self.request('POST', '/api/phone/aka/poll', {'session_id': session_id}, auth)
            self.assertEqual(200, status)
            challenge = body['challenge']
            if challenge:
                self.assertEqual(session_id, challenge['session_id'])
                self.assertTrue(challenge['rand'] == self.rand)
                self.assertTrue(challenge['autn'] == self.autn)
                self.assertGreater(challenge['expires_at'], 0)
                return challenge
            time.sleep(0.01)
        self.fail('The engine request did not reach the authorized polling phone')

    def submit(self, auth, challenge, state='SUCCESS', payload=SUCCESS_PAYLOAD):
        return self.request('POST', '/api/phone/aka/result', {
            'session_id': challenge['session_id'], 'challenge_id': challenge['challenge_id'],
            'state': state, 'payload': payload,
        }, auth)

    def completed(self, pending):
        result = pending.get(timeout=3)
        if isinstance(result, Exception):
            self.fail('Engine HTTP request did not complete successfully: ' + type(result).__name__)
        self.assertEqual(200, result[0])
        return result[2]

    def assert_no_gateway_verification(self, admin):
        status, _, body = self.request('GET', '/api/status', headers=admin)
        self.assertEqual(200, status)
        self.assertIs(body['gateway_installed'], False)
        for stage in body['stages']:
            self.assertEqual('not_tested', stage['status'])
            self.assertIsNone(stage['evidence'])

    def test_synthetic_success_round_trip_does_not_persist_authentication_or_verify_carrier(self):
        admin = self.login()
        phone, auth = self.pair_phone(admin)
        session_id = self.begin(auth)
        self.assertEqual({'challenge': None}, self.request('POST', '/api/phone/aka/poll', {'session_id': session_id}, auth)[2])
        pending = self.begin_engine_request(phone['device_id'])
        challenge = self.await_challenge(auth, session_id)
        self.assertEqual(1, challenge['selected_slot'])
        repeated = self.request('POST', '/api/phone/aka/poll', {'session_id': session_id}, auth)[2]['challenge']
        self.assertTrue(all(repeated[key] == challenge[key] for key in ('session_id', 'challenge_id', 'selected_slot', 'rand', 'autn')), 'Retrying a poll must retain the same bounded challenge')
        self.assertAlmostEqual(repeated['expires_at'], challenge['expires_at'], delta=0.05)
        status, _, ack = self.submit(auth, challenge)
        self.assertEqual((200, {'ok': True}), (status, ack))
        body = self.completed(pending)
        self.assertEqual('SUCCESS', body['state'])
        self.assertTrue(body['payload'] == SUCCESS_PAYLOAD)
        self.assert_no_gateway_verification(admin)
        status, _, devices = self.request('GET', '/api/admin/devices', headers=admin)
        self.assertEqual(200, status)
        serialized = json.dumps(devices)
        for value in (self.rand, self.autn, SUCCESS_PAYLOAD, phone['token'], self.engine_token):
            self.assertFalse(value in serialized)
        # The broker is transient RAM state, not a new report/evidence table.
        for database_file in Path(self.directory.name).glob('*.db*'):
            data = database_file.read_bytes()
            for value in (self.rand, self.autn, SUCCESS_PAYLOAD):
                self.assertFalse(value.encode('ascii') in data)

    def test_privilege_denial_is_returned_without_payload_and_never_becomes_success(self):
        admin = self.login()
        phone, auth = self.pair_phone(admin)
        session_id = self.begin(auth)
        pending = self.begin_engine_request(phone['device_id'])
        challenge = self.await_challenge(auth, session_id)
        self.assertEqual(200, self.submit(auth, challenge, 'CARRIER_PRIVILEGE_REQUIRED', None)[0])
        self.assertEqual({'state': 'CARRIER_PRIVILEGE_REQUIRED', 'payload': None}, self.completed(pending))
        self.assert_no_gateway_verification(admin)

    def test_engine_authentication_is_independent_from_phone_and_admin_credentials(self):
        admin = self.login()
        phone, auth = self.pair_phone(admin)
        body = {'device_id': phone['device_id'], 'rand': self.rand, 'autn': self.autn}
        for headers in ({}, {'Cookie': admin['Cookie']}, auth, {'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}):
            with self.subTest(kind='unauthorized engine credential'):
                status, _, error = self.request('POST', '/api/engine/aka', body, headers)
                self.assertEqual(401, status)
                self.assertFalse(self.rand in json.dumps(error))
                self.assertFalse(self.autn in json.dumps(error))
        self.assertEqual(401, self.request('POST', '/api/phone/aka/session', {'selected_slot': 1}, admin)[0])

    def test_engine_endpoint_rejects_browser_origin_and_proxy_forwarding_even_with_valid_secret(self):
        admin = self.login()
        phone, auth = self.pair_phone(admin)
        session_id = self.begin(auth)
        payload = {'device_id': phone['device_id'], 'rand': self.rand, 'autn': self.autn}
        for name, value in (('Origin', self.origin), ('Origin', ''),
                            ('Forwarded', 'for=127.0.0.1'), ('Forwarded', ''),
                            ('X-Forwarded-Proto', 'https'), ('X-Forwarded-For', '127.0.0.1')):
            with self.subTest(header=name):
                status, _, error = self.request('POST', '/api/engine/aka', payload,
                    {'Authorization': 'Bearer ' + self.engine_token, name: value})
                self.assertEqual((403, {'error': 'local_engine_only'}), (status, error))
                self.assertFalse(self.engine_token in json.dumps(error))
        self.assertEqual({'challenge': None}, self.request('POST', '/api/phone/aka/poll', {'session_id': session_id}, auth)[2])

    def test_engine_rejects_nonstring_and_noncanonical_device_ids_before_database_access(self):
        for identifier in (None, 7, True, {}, [], 'not-a-uuid', '00000000000040008000000000000001'):
            with self.subTest(value_type=type(identifier).__name__):
                status, _, error = self.request('POST', '/api/engine/aka',
                    {'device_id': identifier, 'rand': self.rand, 'autn': self.autn},
                    {'Authorization': 'Bearer ' + self.engine_token})
                self.assertEqual((400, {'error': 'invalid_request'}), (status, error))
                self.assertFalse(self.rand in json.dumps(error))
                self.assertFalse(self.autn in json.dumps(error))
        status, _, body = self.request('POST', '/api/engine/aka',
            {'device_id': '00000000-0000-4000-8000-000000000001', 'rand': self.rand, 'autn': self.autn},
            {'Authorization': 'Bearer ' + self.engine_token})
        self.assertEqual(401, status, 'A canonical UUID still needs an active paired phone')

    def test_engine_endpoint_is_disabled_without_private_token_file(self):
        self.close_server()
        self.engine_file.unlink()
        self.start_server()
        status, _, error = self.request('POST', '/api/engine/aka',
            {'device_id': '00000000-0000-4000-8000-000000000001', 'rand': self.rand, 'autn': self.autn},
            {'Authorization': 'Bearer ' + self.engine_token})
        self.assertEqual(503, status)
        self.assertFalse(self.engine_token in json.dumps(error))

    def test_sync_failure_auts_framing_round_trips_without_claiming_authentication_success(self):
        admin = self.login()
        phone, auth = self.pair_phone(admin)
        session_id = self.begin(auth)
        pending = self.begin_engine_request(phone['device_id'])
        challenge = self.await_challenge(auth, session_id)
        payload = base64.b64encode(bytes([0xDC, 14]) + b'A' * 14).decode('ascii')
        self.assertEqual(200, self.submit(auth, challenge, 'SYNC_FAILURE', payload)[0])
        body = self.completed(pending)
        self.assertEqual('SYNC_FAILURE', body['state'])
        self.assertTrue(body['payload'] == payload)
        self.assert_no_gateway_verification(admin)

    def test_engine_credential_file_rejects_public_permissions_and_symlinks(self):
        self.close_server()
        try:
            self.engine_file.chmod(0o644)
            with self.assertRaises((OSError, ValueError)):
                PanelServer(('127.0.0.1', 0), self.directory.name)
            self.engine_file.chmod(0o600)
            target = self.engine_file.with_name('fixture-private-hash')
            self.engine_file.rename(target)
            self.engine_file.symlink_to(target)
            with self.assertRaises((OSError, ValueError)):
                PanelServer(('127.0.0.1', 0), self.directory.name)
            self.engine_file.unlink()
            target.rename(self.engine_file)
        finally:
            # Keep the normal fixture teardown valid, including on assertion failure.
            if self.engine_file.is_symlink():
                self.engine_file.unlink()
            if not self.engine_file.exists():
                self.engine_file.write_text(hashlib.sha256(self.engine_token.encode('ascii')).hexdigest() + '\n')
            self.engine_file.chmod(0o600)
            self.start_server()

    def test_result_cannot_be_replayed_after_completion(self):
        admin = self.login()
        phone, auth = self.pair_phone(admin)
        session_id = self.begin(auth)
        pending = self.begin_engine_request(phone['device_id'])
        challenge = self.await_challenge(auth, session_id)
        self.assertEqual(200, self.submit(auth, challenge)[0])
        self.completed(pending)
        status, _, error = self.submit(auth, challenge)
        self.assertIn(status, (400, 401))
        self.assertFalse(SUCCESS_PAYLOAD in json.dumps(error))
        self.assertEqual({'challenge': None}, self.request('POST', '/api/phone/aka/poll', {'session_id': session_id}, auth)[2])

    def test_another_paired_phone_cannot_poll_or_answer_the_session(self):
        admin = self.login()
        phone, auth = self.pair_phone(admin)
        _, other_auth = self.pair_phone(admin)
        session_id = self.begin(auth)
        pending = self.begin_engine_request(phone['device_id'])
        challenge = self.await_challenge(auth, session_id)
        self.assertIn(self.request('POST', '/api/phone/aka/poll', {'session_id': session_id}, other_auth)[0], (400, 401))
        self.assertIn(self.submit(other_auth, challenge)[0], (400, 401))
        self.assertEqual(200, self.submit(auth, challenge, 'CARRIER_PRIVILEGE_REQUIRED', None)[0])
        self.assertEqual('CARRIER_PRIVILEGE_REQUIRED', self.completed(pending)['state'])

    def test_revocation_cancels_pending_engine_request_and_blocks_phone(self):
        admin = self.login()
        phone, auth = self.pair_phone(admin)
        session_id = self.begin(auth)
        pending = self.begin_engine_request(phone['device_id'])
        challenge = self.await_challenge(auth, session_id)
        self.assertEqual(200, self.request('POST', '/api/admin/revoke', {'device_id': phone['device_id']}, admin)[0])
        self.assertEqual({'state': 'REVOKED', 'payload': None}, self.completed(pending))
        self.assertEqual(401, self.submit(auth, challenge)[0])
        self.assertEqual(401, self.request('POST', '/api/phone/aka/poll', {'session_id': session_id}, auth)[0])

    def test_stop_cancels_pending_request(self):
        admin = self.login()
        phone, auth = self.pair_phone(admin)
        session_id = self.begin(auth)
        pending = self.begin_engine_request(phone['device_id'])
        self.await_challenge(auth, session_id)
        status, _, body = self.request('POST', '/api/phone/aka/stop', {'session_id': session_id}, auth)
        self.assertEqual((200, {'ok': True}), (status, body))
        self.assertEqual({'state': 'SESSION_STOPPED', 'payload': None}, self.completed(pending))

    def test_invalid_fields_and_payload_are_rejected_without_echoing_authentication_material(self):
        admin = self.login()
        phone, auth = self.pair_phone(admin)
        self.assertEqual(400, self.request('POST', '/api/phone/aka/session', {'selected_slot': 8}, auth)[0])
        session_id = self.begin(auth)
        pending = self.begin_engine_request(phone['device_id'])
        challenge = self.await_challenge(auth, session_id)
        invalid = {'session_id': session_id, 'challenge_id': challenge['challenge_id'],
                   'state': 'SUCCESS', 'payload': SUCCESS_PAYLOAD, 'Ki': 'SYNTHETIC-SECRET-MARKER'}
        status, _, error = self.request('POST', '/api/phone/aka/result', invalid, auth)
        self.assertEqual(400, status)
        for value in (SUCCESS_PAYLOAD, 'SYNTHETIC-SECRET-MARKER', self.rand, self.autn):
            self.assertFalse(value in json.dumps(error))
        self.assertIn(self.submit(auth, challenge, 'SUCCESS', 'not-valid-base64')[0], (400, 401))
        self.assertEqual(200, self.submit(auth, challenge, 'MALFORMED_RESPONSE', None)[0])
        self.assertEqual({'state': 'MALFORMED_RESPONSE', 'payload': None}, self.completed(pending))


if __name__ == '__main__':
    unittest.main()

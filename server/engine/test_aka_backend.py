import base64
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from nexvary_aka_backend import AkaUnavailable, PhoneAkaBackend, get_backend


class Response:
    status = 200
    def __init__(self, data):
        self.data = json.dumps(data).encode() if isinstance(data, dict) else data
    def getheader(self, name, default):
        return 'application/json'
    def read(self, limit):
        return self.data[:limit]


class Connection:
    def __init__(self, response):
        self.response = response
        self.closed = False
        self.sent = None
    def request(self, method, path, body, headers):
        self.sent = method, path, json.loads(body), headers
    def getresponse(self):
        return self.response
    def close(self):
        self.closed = True


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.token = 'private_engine_bearer_' + 'x' * 32
        self.device = str(uuid.uuid4())
        self.backend = PhoneAkaBackend(self.token, self.device)
        self.rand, self.autn = 'AB' * 16, 'CD' * 16
        self.res, self.ck, self.ik = bytes(range(8)), b'c' * 16, b'i' * 16
        self.success = b'\xdb\x08' + self.res + b'\x10' + self.ck + b'\x10' + self.ik

    def call(self, result, method='authenticate'):
        connection = Connection(Response(result))
        with patch('nexvary_aka_backend.http.client.HTTPConnection', return_value=connection) as constructor:
            value = getattr(self.backend, method)(self.rand, self.autn)
        constructor.assert_called_once_with('127.0.0.1', 8787, timeout=35)
        self.assertTrue(connection.closed)
        self.assertEqual(('POST', '/api/engine/aka', {'device_id': self.device, 'rand': self.rand, 'autn': self.autn}), connection.sent[:3])
        self.assertEqual('Bearer ' + self.token, connection.sent[3]['Authorization'])
        return value

    def test_real_db_binary_result_to_upstream_hex(self):
        result = dict(state='SUCCESS', payload=base64.b64encode(self.success).decode())
        self.assertEqual(tuple(x.hex().upper() for x in (self.res, self.ck, self.ik)), self.call(result))
        self.assertEqual(tuple(x.hex().upper() for x in (self.res, self.ck, self.ik)) + (None,), self.call(result, 'authenticate_ami'))

    def test_auts_preserves_actual_swu_and_ami_contracts(self):
        auts = bytes(range(14))
        result = dict(state='SYNC_FAILURE', payload=base64.b64encode(b'\xdc\x0e' + auts).decode())
        self.assertEqual((auts.hex().upper(), None, None), self.call(result))
        self.assertEqual((None, None, None, auts.hex().upper()), self.call(result, 'authenticate_ami'))

    def test_malformed_or_failed_broker_never_returns_fake_vectors(self):
        invalid = [dict(state=state, payload=None) for state in ('AUTHENTICATION_FAILED', 'TIMED_OUT', 'SESSION_INACTIVE', 'REVOKED')]
        invalid += [dict(state='SUCCESS', payload=base64.b64encode(data).decode()) for data in (b'', self.success[:-1], self.success + b'x', b'\xdb\x03' + b'x' * 37, b'\xdb\x08' + self.success[2:10] + b'\x0f' + self.success[11:])]
        invalid += [dict(state='SUCCESS', payload='not base64'), dict(state='SUCCESS', payload=base64.b64encode(self.success).decode(), Ki='secret'), dict(res='00', ck='00', ik='00'), b'invalid', b'x' * 4097]
        for result in invalid:
            with self.subTest(result_type=type(result).__name__), self.assertRaises(AkaUnavailable):
                self.call(result)

    def test_network_exception_is_closed_and_no_credentials_or_challenges_logged(self):
        output = io.StringIO()
        connection = Connection(None)
        secret_error = 'LEAK ' + self.token + self.rand + self.autn
        connection.getresponse = lambda: (_ for _ in ()).throw(OSError(secret_error))
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), patch('nexvary_aka_backend.http.client.HTTPConnection', return_value=connection):
            with self.assertRaises(AkaUnavailable) as caught:
                self.backend.authenticate(self.rand, self.autn)
        self.assertTrue(connection.closed)
        self.assertEqual('', output.getvalue())
        for secret in (self.token, self.rand, self.autn, 'LEAK'):
            self.assertNotIn(secret, str(caught.exception))
            self.assertNotIn(secret, repr(self.backend))

    def test_non_success_http_status_and_wrong_content_type_fail_closed(self):
        for status, kind in ((401, 'application/json'), (302, 'application/json'), (200, 'text/html')):
            response = Response(dict(state='SUCCESS', payload=base64.b64encode(self.success).decode()))
            response.status = status
            response.getheader = lambda *_: kind
            connection = Connection(response)
            with patch('nexvary_aka_backend.http.client.HTTPConnection', return_value=connection), self.assertRaises(AkaUnavailable):
                self.backend.authenticate(self.rand, self.autn)
            self.assertTrue(connection.closed)

    def test_challenge_invalid_before_network_and_identity_not_invented(self):
        with patch('nexvary_aka_backend.http.client.HTTPConnection') as connection:
            for value in ('00', 'GG' * 16, None, b'a' * 32):
                with self.assertRaises(AkaUnavailable):
                    self.backend.authenticate(value, self.autn)
            connection.assert_not_called()
        with self.assertRaises(AkaUnavailable):
            self.backend.identity()

    def test_private_authorization_and_symlink_permissions_secret_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'auth.json'
            path.write_text(json.dumps(dict(token=self.token, device_id=self.device)))
            path.chmod(0o600)
            with patch.dict(os.environ, {'NEXVARY_ENGINE_AUTH_FILE': str(path)}):
                self.assertIsInstance(get_backend(), PhoneAkaBackend)
                path.chmod(0o644)
                with self.assertRaises(AkaUnavailable):
                    get_backend()
                path.chmod(0o600)
                path.write_text(json.dumps(dict(token=self.token, device_id=self.device, Ki='forbidden')))
                with self.assertRaises(AkaUnavailable):
                    get_backend()
            link = Path(directory) / 'link'
            link.symlink_to(path)
            with patch.dict(os.environ, {'NEXVARY_ENGINE_AUTH_FILE': str(link)}), self.assertRaises(AkaUnavailable):
                get_backend()
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(AkaUnavailable):
            get_backend()


if __name__ == '__main__':
    unittest.main()

"""Security and persistence checks for the allowlisted phone-report store."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch
import uuid

from phone_store import MAX_DEVICES, MAX_PAIRINGS, PHONE_CAPABILITIES, PhoneStore


def sample():
    return dict(schema_version=1, sim_count=2, selected_slot=1, network='WIFI',
                phone_as_sim='CARRIER_PRIVILEGE_REQUIRED', app_version='0.3.0-alpha01', android_api=35)


class PhoneStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = PhoneStore(self.directory.name)

    def pair(self):
        return self.store.pair(self.store.create_pairing()['code'])

    def test_persistence_receipt_time_and_no_plaintext_credentials(self):
        with patch('phone_store.time.time', return_value=1000):
            code = self.store.create_pairing()
        self.assertEqual(code['expires_at'], 1600)
        self.assertGreaterEqual(len(code['code']), 22)
        with patch('phone_store.time.time', return_value=1001):
            device = self.store.pair(code['code'])
        self.assertEqual(str(uuid.UUID(device['device_id'])), device['device_id'])
        self.assertGreaterEqual(len(device['token']), 43)
        with patch('phone_store.time.time', return_value=1002):
            result = self.store.report(device['token'], sample())
        self.assertEqual(result['last_seen'], 1002)
        reopened = PhoneStore(self.directory.name)
        self.assertEqual(reopened.list_devices(), [result])
        self.assertEqual(set(result), {'device_id', 'last_seen', 'report'})
        with sqlite3.connect(self.store.path) as database:
            token_hash = database.execute('SELECT token_hash FROM devices').fetchone()[0]
        self.assertEqual(token_hash, hashlib.sha256(device['token'].encode()).hexdigest())
        for path in Path(self.directory.name).iterdir():
            if path.is_file():
                content = path.read_bytes()
                self.assertNotIn(code['code'].encode(), content)
                self.assertNotIn(device['token'].encode(), content)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_pairing_one_use_even_across_concurrent_store_instances(self):
        code = self.store.create_pairing()['code']
        stores = [PhoneStore(self.directory.name) for _ in range(8)]
        def attempt(store):
            try:
                return store.pair(code)
            except PermissionError:
                return None
        with ThreadPoolExecutor(max_workers=8) as executor:
            responses = list(executor.map(attempt, stores))
        self.assertEqual(sum(response is not None for response in responses), 1)
        self.assertEqual(len(self.store.list_devices()), 1)
        with self.assertRaises(PermissionError):
            self.store.pair(code)

    def test_expiry_boundaries_purge_and_pairing_quota(self):
        with patch('phone_store.time.time', return_value=1000):
            codes = [self.store.create_pairing() for _ in range(MAX_PAIRINGS)]
            with self.assertRaises(ValueError):
                self.store.create_pairing()
        with patch('phone_store.time.time', return_value=1600):
            with self.assertRaises(PermissionError):
                self.store.pair(codes[0]['code'])
            fresh = self.store.create_pairing()
            self.assertEqual(len(self.store.list_devices()), 0)
            with sqlite3.connect(self.store.path) as database:
                self.assertEqual(database.execute('SELECT COUNT(*) FROM pairings').fetchone()[0], 1)
            self.store.pair(fresh['code'])

    def test_revocation_removes_authorization_and_frees_capacity(self):
        device = self.pair()
        self.assertTrue(self.store.revoke(device['device_id']))
        self.assertFalse(self.store.revoke(device['device_id']))
        self.assertEqual(self.store.list_devices(), [])
        with self.assertRaises(PermissionError):
            self.store.report(device['token'], sample())

    def test_authenticated_disconnect_revokes_only_the_bound_phone(self):
        first, second = self.pair(), self.pair()
        self.assertTrue(self.store.disconnect(first['token']))
        self.assertEqual([device['device_id'] for device in self.store.list_devices()], [second['device_id']])
        with self.assertRaises(PermissionError):
            self.store.report(first['token'], sample())
        for token in [first['token'], None, 'unknowncredential000000000000']:
            with self.assertRaises(PermissionError):
                self.store.disconnect(token)
        self.store.report(second['token'], sample())

    def test_devices_are_bounded_and_outstanding_code_cannot_exceed_limit(self):
        outstanding = self.store.create_pairing()['code']
        with sqlite3.connect(self.store.path) as database:
            database.executemany('INSERT INTO devices(device_id, token_hash) VALUES (?, ?)',
                                 [(str(uuid.uuid4()), f'{index:064x}') for index in range(MAX_DEVICES)])
        with self.assertRaises(ValueError):
            self.store.create_pairing()
        with self.assertRaises(ValueError):
            self.store.pair(outstanding)
        self.assertTrue(self.store.revoke(self.store.list_devices()[0]['device_id']))
        self.store.pair(outstanding)
        self.assertEqual(len(self.store.list_devices()), MAX_DEVICES)

    def test_unknown_secret_identity_clock_and_gateway_fields_rejected(self):
        token = self.pair()['token']
        for extra in ['Ki', 'ki', 'IMSI', 'imsi', 'carrier', 'phone_number', 'ip', 'timestamp',
                      'aka_response', 'CK', 'IK', 'ims_registered', 'audio_verified', 'device_id']:
            with self.subTest(field=extra):
                report = sample()
                report[extra] = 'must-never-be-stored'
                with self.assertRaises(ValueError):
                    self.store.report(token, report)
        self.assertIsNone(self.store.list_devices()[0]['report'])
        self.assertNotIn(b'must-never-be-stored', self.store.path.read_bytes())

    def test_types_ranges_enums_and_missing_fields_are_rejected(self):
        token = self.pair()['token']
        invalid = {
            'schema_version': [True, 0, 2, '1'], 'sim_count': [True, -1, 9, 1.0],
            'selected_slot': [True, -1, 8, '0'], 'network': ['wifi', {}, 'WIFI\n'],
            'phone_as_sim': ['AKA_VERIFIED', {}, 'READY'],
            'app_version': ['', 'x' * 65, '1.0_1', '1.0\n', '../../secret', '版本1'],
            'android_api': [True, 25, 101, '35'],
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    report = sample()
                    report[field] = value
                    with self.assertRaises(ValueError):
                        self.store.report(token, report)
        for field in sample():
            report = sample()
            del report[field]
            with self.assertRaises(ValueError):
                self.store.report(token, report)
        for payload in [None, [], 'payload']:
            with self.assertRaises(ValueError):
                self.store.report(token, payload)

    def test_all_capability_names_are_accepted_without_gateway_evidence(self):
        token = self.pair()['token']
        for capability in PHONE_CAPABILITIES:
            report = sample()
            report['phone_as_sim'] = capability
            report['selected_slot'] = None
            response = self.store.report(token, report)
            self.assertEqual(response['report'], report)
            self.assertEqual(set(response['report']), set(sample()))

    def test_malformed_or_unknown_credentials_are_not_authorized(self):
        for token in [None, 123, '', 'short', 'x' * 129, '../../token', 'unknowncredential000000000000']:
            with self.subTest(token=token):
                with self.assertRaises(PermissionError):
                    self.store.report(token, sample())
                with self.assertRaises(PermissionError):
                    self.store.pair(token)

    def test_database_symlink_is_rejected_without_touching_target(self):
        other = Path(self.directory.name) / 'target'
        other.write_text('untouched')
        linked = Path(self.directory.name) / 'linked'
        linked.mkdir()
        (linked / 'phones.sqlite3').symlink_to(other)
        with self.assertRaises(OSError):
            PhoneStore(linked)
        self.assertEqual(other.read_text(), 'untouched')


if __name__ == '__main__':
    unittest.main()

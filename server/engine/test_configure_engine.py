import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid

import configure_engine as provision
from nexvary_aka_backend import get_backend


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / 'state'; self.state.mkdir(mode=0o700)
        self.parent = self.root / 'private'; self.parent.mkdir(mode=0o700)
        self.config = self.parent / 'auth.json'
        self.password = self.state / 'password.json'
        self.password.write_text('{"hash":"existing-password-state"}'); self.password.chmod(0o600)
        self.database = self.state / 'phones.sqlite3'
        self.device = str(uuid.uuid4())
        with sqlite3.connect(self.database) as database:
            database.execute('CREATE TABLE devices(device_id TEXT PRIMARY KEY)')
            database.execute('INSERT INTO devices VALUES (?)', (self.device,))
        self.database.chmod(0o600)
        self.original = self.password.read_bytes(), self.database.read_bytes()

    def run_configure(self):
        provision.configure(self.state, self.config, self.device)

    def test_provisions_matching_private_credentials_only_and_adapter_loads(self):
        self.run_configure()
        config = json.loads(self.config.read_text())
        self.assertEqual({'token', 'device_id'}, set(config))
        self.assertEqual(self.device, config['device_id'])
        self.assertGreaterEqual(len(config['token']), 43)
        hashed = self.state / 'engine-token.sha256'
        self.assertEqual(hashlib.sha256(config['token'].encode()).hexdigest(), hashed.read_text().strip())
        for path in (self.config, hashed):
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
        self.assertEqual((self.state.stat().st_uid, self.state.stat().st_gid), (hashed.stat().st_uid, hashed.stat().st_gid))
        self.assertEqual(self.original, (self.password.read_bytes(), self.database.read_bytes()))
        with patch.dict(os.environ, {'NEXVARY_ENGINE_AUTH_FILE': str(self.config)}):
            self.assertEqual('<PhoneAkaBackend: private credentials>', repr(get_backend()))
        self.assertEqual({'password.json', 'phones.sqlite3', 'engine-token.sha256'}, {p.name for p in self.state.iterdir()})

    def test_existing_files_or_symlinks_are_never_overwritten(self):
        for kind in ('config', 'hash', 'link'):
            with self.subTest(kind=kind):
                target = self.config if kind in ('config', 'link') else self.state / 'engine-token.sha256'
                if kind == 'link': target.symlink_to(self.password)
                else: target.write_text('existing')
                with self.assertRaises(ValueError): self.run_configure()
                if kind == 'link': self.assertTrue(target.is_symlink())
                else: self.assertEqual('existing', target.read_text())
                target.unlink()
        self.assertEqual(self.original, (self.password.read_bytes(), self.database.read_bytes()))

    def test_second_file_failure_rolls_back_new_config(self):
        original_writer = provision._write_new
        def writer(directory, name, *args):
            if name == 'engine-token.sha256': raise OSError('controlled fixture')
            return original_writer(directory, name, *args)
        with patch.object(provision, '_write_new', side_effect=writer), self.assertRaises(OSError): self.run_configure()
        self.assertFalse(self.config.exists())
        self.assertFalse((self.state / 'engine-token.sha256').exists())
        self.assertEqual(self.original, (self.password.read_bytes(), self.database.read_bytes()))

    def test_unknown_device_and_malformed_uuid_create_nothing(self):
        for device in (str(uuid.uuid4()), 'not-a-uuid'):
            with self.assertRaises(ValueError): provision.configure(self.state, self.config, device)
        self.assertFalse(self.config.exists())
        self.assertFalse((self.state / 'engine-token.sha256').exists())

    def test_private_permissions_enforced_before_writes(self):
        for path, mode in ((self.state, 0o750), (self.parent, 0o755), (self.password, 0o644), (self.database, 0o644)):
            old = path.stat().st_mode & 0o777; path.chmod(mode)
            with self.subTest(path=path.name), self.assertRaises(ValueError): self.run_configure()
            path.chmod(old)
        self.assertFalse(self.config.exists())

    def test_symlink_parent_state_or_database_refused(self):
        linked_parent = self.root / 'linked'; linked_parent.symlink_to(self.parent)
        with self.assertRaises(OSError): provision.configure(self.state, linked_parent / 'auth.json', self.device)
        linked_state = self.root / 'linked-state'; linked_state.symlink_to(self.state)
        with self.assertRaises(OSError): provision.configure(linked_state, self.config, self.device)
        self.database.rename(self.state / 'real-db')
        self.database.symlink_to(self.state / 'real-db')
        with self.assertRaises(OSError): self.run_configure()
        self.assertFalse(self.config.exists())

    def test_pending_wal_refused_instead_of_stale_authorization_read(self):
        wal = self.state / 'phones.sqlite3-wal'; wal.write_bytes(b'pending-fixture')
        with self.assertRaises(ValueError): self.run_configure()
        self.assertFalse(self.config.exists())


if __name__ == '__main__':
    unittest.main()

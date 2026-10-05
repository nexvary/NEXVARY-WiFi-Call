"""Private, bounded phone pairing and strictly allowlisted capability reports.

No SIM identifier, authentication challenge/result, gateway evidence or plaintext
pairing/bearer credential is persisted. All times are receipt times on the server.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import threading
import time
import uuid

REPORT_FIELDS = frozenset({
    'schema_version', 'sim_count', 'selected_slot', 'network',
    'phone_as_sim', 'app_version', 'android_api',
})
NETWORKS = frozenset({'WIFI', 'CELLULAR', 'OTHER', 'NONE', 'UNKNOWN'})
PHONE_CAPABILITIES = frozenset({
    'AVAILABLE_BY_CARRIER_PRIVILEGE', 'NO_ACTIVE_SUBSCRIPTION',
    'TELEPHONY_UNAVAILABLE', 'CARRIER_PRIVILEGE_REQUIRED', 'PERMISSION_REQUIRED',
    'UNSUPPORTED', 'SIM_NOT_SELECTED', 'UNKNOWN',  # UNKNOWN is report-only: not checked.
})
VERSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9.-]{0,63}\Z', re.ASCII)
CREDENTIAL = re.compile(r'[A-Za-z0-9_-]{22,128}\Z', re.ASCII)
PAIRING_TTL = 600
MAX_PAIRINGS = 10
MAX_DEVICES = 200


def _digest(value):
    if not isinstance(value, str) or CREDENTIAL.fullmatch(value) is None:
        raise ValueError('Invalid credential format.')
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def _report(payload):
    if not isinstance(payload, dict) or set(payload) != REPORT_FIELDS:
        raise ValueError('Report must contain exactly the supported fields.')
    if type(payload['schema_version']) is not int or payload['schema_version'] != 1:
        raise ValueError('Unsupported report schema.')
    for key, low, high in (('sim_count', 0, 8), ('android_api', 26, 100)):
        if type(payload[key]) is not int or not low <= payload[key] <= high:
            raise ValueError('Report integer outside supported range.')
    selected = payload['selected_slot']
    if selected is not None and (type(selected) is not int or not 0 <= selected <= 7):
        raise ValueError('Invalid selected slot.')
    if not isinstance(payload['network'], str) or payload['network'] not in NETWORKS:
        raise ValueError('Unsupported network state.')
    if not isinstance(payload['phone_as_sim'], str) or payload['phone_as_sim'] not in PHONE_CAPABILITIES:
        raise ValueError('Unsupported phone capability state.')
    version = payload['app_version']
    if not isinstance(version, str) or VERSION.fullmatch(version) is None:
        raise ValueError('Invalid application version.')
    return {key: payload[key] for key in sorted(REPORT_FIELDS)}


class PhoneStore:
    def __init__(self, state_dir):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.state_dir / 'phones.sqlite3'
        self._lock = threading.RLock()
        flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(self.path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('Phone database must be a regular file.')
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        with self._connection() as database:
            database.execute('PRAGMA journal_mode=WAL')
            database.execute('''CREATE TABLE IF NOT EXISTS pairings (
                code_hash TEXT PRIMARY KEY, expires_at REAL NOT NULL
            )''')
            database.execute('''CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL,
                last_seen REAL, report TEXT
            )''')

    @contextmanager
    def _connection(self):
        # A fresh connection per operation avoids SQLite thread affinity. BEGIN
        # IMMEDIATE also serializes independent PhoneStore instances/processes.
        with self._lock:
            database = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            database.row_factory = sqlite3.Row
            try:
                yield database
            except BaseException:
                if database.in_transaction:
                    database.rollback()
                raise
            finally:
                database.close()

    def create_pairing(self):
        now = time.time()
        code = secrets.token_urlsafe(32)
        expires = now + PAIRING_TTL
        with self._connection() as database:
            database.execute('BEGIN IMMEDIATE')
            database.execute('DELETE FROM pairings WHERE expires_at <= ?', (now,))
            count = database.execute('SELECT COUNT(*) FROM pairings').fetchone()[0]
            if count >= MAX_PAIRINGS:
                raise ValueError('Too many active pairing codes.')
            if database.execute('SELECT COUNT(*) FROM devices').fetchone()[0] >= MAX_DEVICES:
                raise ValueError('Device limit reached; revoke a device first.')
            database.execute('INSERT INTO pairings(code_hash, expires_at) VALUES (?, ?)', (_digest(code), expires))
            database.commit()
        return {'code': code, 'expires_at': expires}

    def pair(self, code):
        try:
            code_hash = _digest(code)
        except ValueError:
            raise PermissionError('Pairing code invalid, expired or already used.') from None
        now = time.time()
        device_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        with self._connection() as database:
            database.execute('BEGIN IMMEDIATE')
            pairing = database.execute('SELECT expires_at FROM pairings WHERE code_hash = ?', (code_hash,)).fetchone()
            if pairing is None or pairing['expires_at'] <= now:
                raise PermissionError('Pairing code invalid, expired or already used.')
            if database.execute('SELECT COUNT(*) FROM devices').fetchone()[0] >= MAX_DEVICES:
                raise ValueError('Device limit reached; revoke a device first.')
            database.execute('INSERT INTO devices(device_id, token_hash) VALUES (?, ?)', (device_id, _digest(token)))
            database.execute('DELETE FROM pairings WHERE code_hash = ?', (code_hash,))
            database.commit()
        return {'device_id': device_id, 'token': token}

    def report(self, token, payload):
        try:
            token_hash = _digest(token)
        except ValueError:
            raise PermissionError('Device is not authorized.') from None
        with self._connection() as database:
            database.execute('BEGIN IMMEDIATE')
            device = database.execute('SELECT device_id FROM devices WHERE token_hash = ?', (token_hash,)).fetchone()
            if device is None:
                raise PermissionError('Device is not authorized.')
            report = _report(payload)
            received_at = time.time()
            database.execute('UPDATE devices SET last_seen = ?, report = ? WHERE device_id = ?',
                             (received_at, json.dumps(report, sort_keys=True, separators=(',', ':')), device['device_id']))
            database.commit()
        return {'device_id': device['device_id'], 'last_seen': received_at, 'report': report}

    def disconnect(self, token):
        try:
            token_hash = _digest(token)
        except ValueError:
            raise PermissionError('Device is not authorized.') from None
        with self._connection() as database:
            database.execute('BEGIN IMMEDIATE')
            result = database.execute('DELETE FROM devices WHERE token_hash = ?', (token_hash,))
            if result.rowcount != 1:
                raise PermissionError('Device is not authorized.')
            database.commit()
        return True

    def list_devices(self):
        with self._connection() as database:
            rows = database.execute('SELECT device_id, last_seen, report FROM devices ORDER BY device_id').fetchall()
        return [{'device_id': row['device_id'], 'last_seen': row['last_seen'],
                 'report': json.loads(row['report']) if row['report'] is not None else None} for row in rows]

    def revoke(self, device_id):
        if not isinstance(device_id, str):
            return False
        with self._connection() as database:
            database.execute('BEGIN IMMEDIATE')
            result = database.execute('DELETE FROM devices WHERE device_id = ?', (device_id,))
            database.commit()
        return result.rowcount == 1

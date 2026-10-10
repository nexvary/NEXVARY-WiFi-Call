"""Bounded, in-memory relay for explicit, paired-phone EAP-AKA sessions.

The HTTP boundary must authorize the bearer credential before every operation and
call revoke() when pairing is revoked. This module never authenticates a carrier,
opens a SIM, logs request/result material, writes files, or establishes IMS evidence.
"""
import base64
import binascii
from collections import deque
import hashlib
import re
import secrets
import threading
import time

DEVICE = re.compile(r'[A-Za-z0-9_-]{1,128}\Z', re.ASCII)
IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{32,128}\Z', re.ASCII)
HEX_CHALLENGE = re.compile(r'[A-Fa-f0-9]{32}\Z', re.ASCII)
ERROR_STATES = frozenset({
    'CARRIER_PRIVILEGE_REQUIRED', 'PERMISSION_REQUIRED', 'NO_ACTIVE_SIM',
    'TELEPHONY_UNAVAILABLE', 'UNSUPPORTED', 'SIM_NOT_SELECTED',
    'AUTHENTICATION_FAILED', 'MALFORMED_RESPONSE', 'SUBSCRIPTION_CHANGED',
})
RESULT_STATES = ERROR_STATES | {'SUCCESS', 'SYNC_FAILURE'}


class AkaBrokerError(ValueError):
    """Safe machine code only; never interpolate supplied identifiers or payloads."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _wipe(value):
    if value is not None:
        for index in range(len(value)):
            value[index] = 0


class AkaResult:
    """Engine-only, transient response. repr/str never contain authentication data.

    The caller must clear() promptly after consumption and must not put to_dict()
    in panel inventory, diagnostic exports, logs or a database. Python cannot
    guarantee erasure of temporary/interpreter copies.
    """
    __slots__ = ('state', '_raw')

    def __init__(self, state, raw=None):
        self.state = state
        self._raw = raw

    @property
    def payload(self):
        return base64.b64encode(self._raw).decode('ascii') if self._raw is not None else None

    def to_dict(self):
        return {'state': self.state, 'payload': self.payload}

    def clear(self):
        _wipe(self._raw)
        self._raw = None

    def __repr__(self):
        return 'AkaResult(state=%s, payload=redacted)' % self.state

    def __del__(self):
        self.clear()


def _parse_result(payload):
    if not isinstance(payload, dict) or set(payload) != {'challenge_id', 'state', 'payload'}:
        raise AkaBrokerError('INVALID_RESULT')
    identifier = payload['challenge_id']
    state = payload['state']
    encoded = payload['payload']
    if not isinstance(identifier, str) or IDENTIFIER.fullmatch(identifier) is None:
        raise AkaBrokerError('INVALID_RESULT')
    if not isinstance(state, str) or state not in RESULT_STATES:
        raise AkaBrokerError('INVALID_RESULT')
    if state in ERROR_STATES:
        if encoded is not None:
            raise AkaBrokerError('INVALID_RESULT')
        return identifier, AkaResult(state)
    if not isinstance(encoded, str) or not 1 <= len(encoded) <= 72:
        raise AkaBrokerError('INVALID_RESULT')
    raw = None
    try:
        decoded = base64.b64decode(encoded, validate=True)
        # Reject noncanonical padding, trailing data and non-ASCII encodings.
        if base64.b64encode(decoded).decode('ascii') != encoded:
            raise AkaBrokerError('INVALID_RESULT')
        raw = bytearray(decoded)
        if state == 'SYNC_FAILURE':
            valid = len(raw) == 16 and raw[0] == 0xDC and raw[1] == 14
        else:
            valid = 40 <= len(raw) <= 52 and raw[0] == 0xDB and 4 <= raw[1] <= 16
            if valid:
                position = 2 + raw[1]
                valid = position < len(raw) and raw[position] == 16
                position += 17
                valid = valid and position < len(raw) and raw[position] == 16
                position += 17
                valid = valid and position == len(raw)
        if not valid:
            raise AkaBrokerError('INVALID_RESULT')
        return identifier, AkaResult(state, raw)
    except (ValueError, UnicodeError, binascii.Error):
        _wipe(raw)
        raise AkaBrokerError('INVALID_RESULT') from None


class _Challenge:
    __slots__ = ('identifier', 'rand', 'autn', 'deadline', 'real_deadline', 'expires_at', 'result', 'closed_state')

    def __init__(self, rand, autn, now, ttl, expires_at):
        self.identifier = secrets.token_urlsafe(32)
        self.rand = bytearray.fromhex(rand)
        self.autn = bytearray.fromhex(autn)
        self.deadline = now + ttl
        self.real_deadline = time.monotonic() + ttl
        self.expires_at = expires_at
        self.result = None
        self.closed_state = None

    def clear_material(self):
        _wipe(self.rand)
        _wipe(self.autn)
        if self.result is not None:
            self.result.clear()
            self.result = None

    def __repr__(self):
        return '_Challenge(redacted)'


class _Session:
    __slots__ = ('identifier', 'slot', 'deadline', 'challenge', 'closed_state',
                 'expires_at', 'last_state', 'response_received', 'last_request', 'seen')

    def __init__(self, slot, now, ttl, expires_at):
        self.identifier = secrets.token_urlsafe(32)
        self.slot = slot
        self.deadline = now + ttl
        self.expires_at = expires_at
        self.challenge = None
        self.closed_state = None
        self.last_state = 'NOT_TESTED'
        self.response_received = False
        self.last_request = None
        self.seen = set()

    def __repr__(self):
        return '_Session(redacted)'


class AkaBroker:
    def __init__(self, *, clock=time.monotonic, wall_clock=time.time,
                 session_ttl=300, challenge_ttl=30, max_sessions=200,
                 request_interval=1, begin_interval=1):
        if not 0 < session_ttl <= 300 or not 0 < challenge_ttl <= 30:
            raise ValueError('Invalid lifetime bounds.')
        if type(max_sessions) is not int or not 1 <= max_sessions <= 200:
            raise ValueError('Invalid session bound.')
        if not 0 <= request_interval <= 30 or not 0 <= begin_interval <= 300:
            raise ValueError('Invalid retry bounds.')
        self._clock = clock
        self._wall_clock = wall_clock
        self._session_ttl = session_ttl
        self._challenge_ttl = challenge_ttl
        self._max_sessions = max_sessions
        self._request_interval = request_interval
        self._begin_interval = begin_interval
        self._condition = threading.Condition(threading.RLock())
        self._sessions = {}
        # Bounded retry metadata, containing device IDs/times only, never SIM material.
        self._begins = {}
        self._requests = {}

    @staticmethod
    def _device(device_id):
        if not isinstance(device_id, str) or DEVICE.fullmatch(device_id) is None:
            raise AkaBrokerError('INVALID_DEVICE')

    def _close(self, session, state):
        session.closed_state = state
        challenge = session.challenge
        if challenge is not None:
            challenge.closed_state = state
            challenge.clear_material()
            session.challenge = None
        session.seen.clear()
        self._condition.notify_all()

    def _purge(self, now):
        for device_id, session in list(self._sessions.items()):
            if session.deadline <= now:
                self._close(session, 'SESSION_EXPIRED')
                del self._sessions[device_id]
            elif session.challenge is not None:
                challenge = session.challenge
                if challenge.deadline <= now or challenge.real_deadline <= time.monotonic():
                    challenge.closed_state = 'TIMEOUT'
                    challenge.clear_material()
                    session.challenge = None
                    session.last_state = 'TIMEOUT'
                    self._condition.notify_all()
        for history_map in (self._begins, self._requests):
            for key, history in list(history_map.items()):
                while history and now - history[0] >= 60:
                    history.popleft()
                if not history:
                    del history_map[key]

    def _session(self, device_id, identifier, now):
        self._device(device_id)
        self._purge(now)
        session = self._sessions.get(device_id)
        if session is None or not isinstance(identifier, str) or not secrets.compare_digest(session.identifier, identifier):
            raise AkaBrokerError('SESSION_OFF')
        return session

    def begin(self, device_id, slot):
        self._device(device_id)
        if type(slot) is not int or not 0 <= slot <= 7:
            raise AkaBrokerError('INVALID_SLOT')
        with self._condition:
            now = self._clock()
            self._purge(now)
            if device_id in self._sessions:
                raise AkaBrokerError('SESSION_ACTIVE')
            history = self._begins.get(device_id, ())
            if len(history) >= 5 or (history and now - history[-1] < self._begin_interval):
                raise AkaBrokerError('RATE_LIMITED')
            if len(self._sessions) >= self._max_sessions or len(self._begins) >= self._max_sessions:
                raise AkaBrokerError('CAPACITY')
            session = _Session(slot, now, self._session_ttl, int(self._wall_clock() + self._session_ttl))
            self._sessions[device_id] = session
            self._begins.setdefault(device_id, deque()).append(now)
            return {'session_id': session.identifier, 'selected_slot': slot,
                    'expires_at': session.expires_at}

    def stop(self, device_id, session_id):
        with self._condition:
            session = self._session(device_id, session_id, self._clock())
            self._close(session, 'SESSION_STOPPED')
            del self._sessions[device_id]
            return True

    def revoke(self, device_id):
        self._device(device_id)
        with self._condition:
            session = self._sessions.pop(device_id, None)
            if session is not None:
                self._close(session, 'REVOKED')
            return session is not None

    def poll(self, device_id, session_id):
        with self._condition:
            now = self._clock()
            session = self._session(device_id, session_id, now)
            challenge = session.challenge
            if challenge is None or challenge.result is not None or challenge.closed_state is not None:
                return None
            # A failed HTTP delivery may be retried; the same challenge is returned
            # until submission. Android must deduplicate actual UICC computation.
            return {'session_id': session.identifier, 'challenge_id': challenge.identifier,
                    'selected_slot': session.slot, 'rand': challenge.rand.hex(),
                    'autn': challenge.autn.hex(),
                    'expires_at': challenge.expires_at}

    def submit(self, device_id, session_id, payload):
        with self._condition:
            session = self._session(device_id, session_id, self._clock())
            identifier, result = _parse_result(payload)
            challenge = session.challenge
            if challenge is None or not secrets.compare_digest(challenge.identifier, identifier):
                result.clear()
                raise AkaBrokerError('UNKNOWN_CHALLENGE')
            if challenge.result is not None or challenge.closed_state is not None:
                result.clear()
                raise AkaBrokerError('REPLAY')
            challenge.result = result
            session.last_state = result.state
            # This is receipt of a framed response, not carrier/IMS authentication proof.
            session.response_received = result.state == 'SUCCESS'
            self._condition.notify_all()
            return {'ok': True}

    def request(self, device_id, rand_hex, autn_hex):
        self._device(device_id)
        if any(not isinstance(value, str) or HEX_CHALLENGE.fullmatch(value) is None
               for value in (rand_hex, autn_hex)):
            raise AkaBrokerError('INVALID_CHALLENGE')
        with self._condition:
            now = self._clock()
            self._purge(now)
            session = self._sessions.get(device_id)
            if session is None:
                raise AkaBrokerError('SESSION_OFF')
            if session.challenge is not None:
                raise AkaBrokerError('BUSY')
            if session.last_request is not None and now - session.last_request < self._request_interval:
                raise AkaBrokerError('RATE_LIMITED')
            history = self._requests.get(device_id, ())
            if len(history) >= 5 or (history and now - history[-1] < self._request_interval):
                raise AkaBrokerError('RATE_LIMITED')
            if device_id not in self._requests and len(self._requests) >= self._max_sessions:
                raise AkaBrokerError('CAPACITY')
            fingerprint = hashlib.sha256(bytes.fromhex(rand_hex + autn_hex)).digest()
            if fingerprint in session.seen:
                raise AkaBrokerError('REPLAY')
            if len(session.seen) >= 32:
                raise AkaBrokerError('SESSION_LIMIT')
            session.seen.add(fingerprint)
            session.last_request = now
            self._requests.setdefault(device_id, deque()).append(now)
            ttl = min(self._challenge_ttl, session.deadline - now)
            challenge = _Challenge(rand_hex, autn_hex, now, ttl,
                                   int(self._wall_clock() + ttl))
            session.challenge = challenge
            while True:
                now = self._clock()
                self._purge(now)
                if session.closed_state is not None or challenge.closed_state is not None:
                    state = session.closed_state or challenge.closed_state
                    challenge.clear_material()
                    return AkaResult(state)
                if challenge.result is not None:
                    # Detach once for this unique engine waiter. No result remains in
                    # broker/session/status after ownership transfers to the engine.
                    result = challenge.result
                    challenge.result = None
                    challenge.clear_material()
                    session.challenge = None
                    self._condition.notify_all()
                    return result
                remaining = min(challenge.deadline - now,
                                challenge.real_deadline - time.monotonic(), session.deadline - now)
                if remaining <= 0:
                    challenge.closed_state = 'TIMEOUT'
                    continue
                self._condition.wait(timeout=min(remaining, 1))

    def status(self, device_id):
        self._device(device_id)
        with self._condition:
            now = self._clock()
            self._purge(now)
            session = self._sessions.get(device_id)
            if session is None:
                return {'session_active': False, 'last_state': 'NOT_TESTED', 'response_received': False}
            return {'session_active': True, 'selected_slot': session.slot,
                    'expires_at': session.expires_at,
                    'last_state': session.last_state, 'response_received': session.response_received}

    def __repr__(self):
        return 'AkaBroker(in-memory, material=redacted)'

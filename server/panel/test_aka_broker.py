"""Synthetic AKA fixtures only; no live SIM/carrier credentials are used."""
import base64
import json
import queue
import threading
import time
import unittest

from aka_broker import AkaBroker, AkaBrokerError, AkaResult, ERROR_STATES


class FakeClock:
    def __init__(self):
        self.value = 1000.0
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            return self.value

    def advance(self, seconds):
        with self.lock:
            self.value += seconds


def success(res_length=4):
    return base64.b64encode(bytes([0xDB, res_length]) + b'R' * res_length +
                            bytes([16]) + b'C' * 16 + bytes([16]) + b'I' * 16).decode('ascii')


def sync_failure():
    return base64.b64encode(bytes([0xDC, 14]) + b'A' * 14).decode('ascii')


class AkaBrokerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.broker = AkaBroker(clock=self.clock, wall_clock=lambda: 1_700_000_000 + self.clock(),
                                challenge_ttl=.4, request_interval=0, begin_interval=0)
        self.session = self.broker.begin('phone-A', 1)
        self.workers = []

    def tearDown(self):
        self.broker.revoke('phone-A')
        self.broker.revoke('phone-B')
        for worker, _ in self.workers:
            worker.join(timeout=1)
            self.assertFalse(worker.is_alive(), 'Engine wait did not terminate.')

    def assertError(self, code, function, *args):
        with self.assertRaises(AkaBrokerError) as caught:
            function(*args)
        self.assertEqual(code, caught.exception.code)
        self.assertEqual(code, str(caught.exception))

    def start(self, index=1, device='phone-A', session=None):
        outputs = queue.Queue()
        def engine():
            try:
                outputs.put(self.broker.request(device, format(index, '032x'), 'ab' * 16))
            except Exception as error:
                outputs.put(error)
        worker = threading.Thread(target=engine, daemon=True)
        worker.start()
        self.workers.append((worker, outputs))
        deadline = time.monotonic() + 1
        identifier = (session or self.session)['session_id']
        while time.monotonic() < deadline:
            pending = self.broker.poll(device, identifier)
            if pending is not None:
                return worker, outputs, pending
            time.sleep(.001)
        self.fail('Engine did not enqueue a challenge.')

    def submit(self, challenge, state='SUCCESS', payload=None, device='phone-A', session=None):
        return self.broker.submit(device, (session or self.session)['session_id'], {
            'challenge_id': challenge['challenge_id'], 'state': state,
            'payload': success() if payload is None and state == 'SUCCESS' else payload,
        })

    def receive(self, outputs):
        result = outputs.get(timeout=1)
        if isinstance(result, Exception):
            raise result
        return result

    def test_session_and_challenge_bind_slot_and_device(self):
        worker, outputs, challenge = self.start()
        self.assertEqual(1, challenge['selected_slot'])
        self.assertEqual(self.session['session_id'], challenge['session_id'])
        self.assertGreater(challenge['expires_at'], 1_700_000_000)
        self.assertIs(type(self.session['expires_at']), int)
        self.assertIs(type(challenge['expires_at']), int)
        self.assertIs(type(self.broker.status('phone-A')['expires_at']), int)
        self.assertEqual(challenge, self.broker.poll('phone-A', self.session['session_id']))
        self.assertError('SESSION_OFF', self.broker.poll, 'phone-B', self.session['session_id'])
        self.assertError('SESSION_OFF', self.broker.submit, 'phone-B', self.session['session_id'], {
            'challenge_id': challenge['challenge_id'], 'state': 'SUCCESS', 'payload': success()})
        self.submit(challenge)
        result = self.receive(outputs)
        self.assertEqual('SUCCESS', result.state)
        self.assertEqual(success(), result.payload)
        result.clear()
        self.assertIsNone(result.payload)
        worker.join(timeout=1)
        self.assertIsNone(self.broker.poll('phone-A', self.session['session_id']))

    def test_session_off_never_queues_authentication(self):
        self.broker.stop('phone-A', self.session['session_id'])
        self.assertError('SESSION_OFF', self.broker.request, 'phone-A', '01' * 16, '02' * 16)
        self.assertError('SESSION_OFF', self.broker.poll, 'phone-A', self.session['session_id'])
        self.assertFalse(self.broker.status('phone-A')['session_active'])

    def test_one_outstanding_request_and_result_single_consumption(self):
        _, outputs, challenge = self.start()
        self.assertError('BUSY', self.broker.request, 'phone-A', '02' * 16, '03' * 16)
        self.submit(challenge)
        result = self.receive(outputs)
        result.clear()
        self.assertError('UNKNOWN_CHALLENGE', self.broker.submit, 'phone-A', self.session['session_id'], {
            'challenge_id': challenge['challenge_id'], 'state': 'SUCCESS', 'payload': success()})
        self.assertError('REPLAY', self.broker.request, 'phone-A', format(1, '032x'), 'ab' * 16)

    def test_synchronization_failure_is_not_success(self):
        _, outputs, challenge = self.start()
        self.submit(challenge, 'SYNC_FAILURE', sync_failure())
        result = self.receive(outputs)
        self.assertEqual({'state': 'SYNC_FAILURE', 'payload': sync_failure()}, result.to_dict())
        self.assertFalse(self.broker.status('phone-A')['response_received'])
        result.clear()

    def test_denial_states_are_distinct_and_have_no_payload(self):
        # A separate broker per synthetic state keeps the five-per-minute limit intact.
        for state in sorted(ERROR_STATES):
            with self.subTest(state=state):
                self.broker.revoke('phone-A')
                self.broker = AkaBroker(challenge_ttl=.4, request_interval=0, begin_interval=0)
                self.session = self.broker.begin('phone-A', 0)
                _, outputs, challenge = self.start()
                self.submit(challenge, state, None)
                result = self.receive(outputs)
                self.assertEqual({'state': state, 'payload': None}, result.to_dict())
                self.assertEqual(state, self.broker.status('phone-A')['last_state'])
                self.assertFalse(self.broker.status('phone-A')['response_received'])

    def test_selected_slot_cannot_change_in_place(self):
        self.assertError('SESSION_ACTIVE', self.broker.begin, 'phone-A', 0)
        _, outputs, challenge = self.start()
        self.broker.stop('phone-A', self.session['session_id'])
        self.assertEqual('SESSION_STOPPED', self.receive(outputs).state)
        replacement = self.broker.begin('phone-A', 0)
        self.assertNotEqual(self.session['session_id'], replacement['session_id'])
        self.assertError('SESSION_OFF', self.broker.submit, 'phone-A', self.session['session_id'], {
            'challenge_id': challenge['challenge_id'], 'state': 'SUCCESS', 'payload': success()})

    def test_revocation_aborts_waiter_and_wipes_pending_material(self):
        _, outputs, challenge = self.start()
        pending = self.broker._sessions['phone-A'].challenge
        self.assertTrue(self.broker.revoke('phone-A'))
        self.assertEqual('REVOKED', self.receive(outputs).state)
        self.assertTrue(all(value == 0 for value in pending.rand + pending.autn))
        self.assertIsNone(pending.result)
        self.assertError('SESSION_OFF', self.broker.submit, 'phone-A', self.session['session_id'], {
            'challenge_id': challenge['challenge_id'], 'state': 'SUCCESS', 'payload': success()})

    def test_challenge_expiry_rejects_late_response(self):
        _, outputs, challenge = self.start()
        self.clock.advance(1)
        self.assertIsNone(self.broker.poll('phone-A', self.session['session_id']))
        self.assertEqual('TIMEOUT', self.receive(outputs).state)
        self.assertError('UNKNOWN_CHALLENGE', self.broker.submit, 'phone-A', self.session['session_id'], {
            'challenge_id': challenge['challenge_id'], 'state': 'SUCCESS', 'payload': success()})

    def test_session_expiry_aborts_waiter(self):
        _, outputs, _ = self.start()
        self.clock.advance(301)
        self.assertFalse(self.broker.status('phone-A')['session_active'])
        self.assertEqual('SESSION_EXPIRED', self.receive(outputs).state)

    def test_real_wait_is_bounded_even_when_fake_clock_does_not_move(self):
        self.broker.revoke('phone-A')
        self.broker = AkaBroker(clock=self.clock, challenge_ttl=.03)
        self.session = self.broker.begin('phone-A', 0)
        started = time.monotonic()
        result = self.broker.request('phone-A', '01' * 16, '02' * 16)
        self.assertEqual('TIMEOUT', result.state)
        self.assertLess(time.monotonic() - started, .5)
        self.assertIsNone(self.broker._sessions['phone-A'].challenge)

    def test_result_parser_rejects_trailing_bytes_wrong_lengths_and_secret_fields(self):
        _, outputs, challenge = self.start()
        valid = {'challenge_id': challenge['challenge_id'], 'state': 'SUCCESS', 'payload': success()}
        invalid = [dict(valid, ki='forbidden'), dict(valid, state='AKA_VERIFIED'),
                   dict(valid, payload='not base64!'), dict(valid, payload=success() + '\n'),
                   dict(valid, payload=base64.b64encode(base64.b64decode(success()) + b'x').decode()),
                   dict(valid, payload=success(3)), dict(valid, payload=success(17)),
                   dict(valid, payload=sync_failure()),
                   dict(valid, state='SYNC_FAILURE', payload=success()),
                   dict(valid, state='CARRIER_PRIVILEGE_REQUIRED', payload='forbidden'),
                   dict(valid, payload=base64.b64encode(bytes([0xDB, 4]) + b'R'*4 + bytes([15])+b'C'*15+bytes([16])+b'I'*16).decode())]
        for payload in invalid:
            with self.subTest(shape=list(payload)):
                self.assertError('INVALID_RESULT', self.broker.submit, 'phone-A', self.session['session_id'], payload)
        self.submit(challenge)
        self.receive(outputs).clear()

    def test_success_res_bounds_and_fixed_ck_ik_lengths(self):
        for length in (4, 16):
            _, outputs, challenge = self.start(index=length)
            self.submit(challenge, payload=success(length))
            result = self.receive(outputs)
            self.assertEqual(success(length), result.payload)
            result.clear()

    def test_begin_and_challenge_retry_limits_survive_session_restarts(self):
        self.broker.stop('phone-A', self.session['session_id'])
        for _ in range(4):
            opened = self.broker.begin('phone-A', 0)
            self.broker.stop('phone-A', opened['session_id'])
        self.assertError('RATE_LIMITED', self.broker.begin, 'phone-A', 0)
        self.clock.advance(61)
        self.session = self.broker.begin('phone-A', 0)
        for index in range(5):
            _, outputs, challenge = self.start(index + 10)
            self.submit(challenge, 'AUTHENTICATION_FAILED', None)
            self.receive(outputs).clear()
        self.broker.stop('phone-A', self.session['session_id'])
        self.session = self.broker.begin('phone-A', 0)
        self.assertError('RATE_LIMITED', self.broker.request, 'phone-A', 'ff' * 16, 'ab' * 16)
        self.clock.advance(61)
        _, outputs, challenge = self.start(30)
        self.submit(challenge, 'AUTHENTICATION_FAILED', None)
        self.receive(outputs).clear()

    def test_capacity_bounds_and_argument_validation(self):
        small = AkaBroker(max_sessions=1)
        small.begin('one', 0)
        self.assertError('CAPACITY', small.begin, 'two', 0)
        for slot in (-1, 8, True, '0'):
            self.assertError('INVALID_SLOT', self.broker.begin, 'phone-B', slot)
        for value in ('', 'g' * 32, 'ab' * 15, None):
            self.assertError('INVALID_CHALLENGE', self.broker.request, 'phone-A', value, 'ab' * 16)
        with self.assertRaises(ValueError):
            AkaBroker(max_sessions=201)
        with self.assertRaises(ValueError):
            AkaBroker(challenge_ttl=31)
        with self.assertRaises(ValueError):
            AkaBroker(session_ttl=301)
        small.revoke('one')

    def test_inventory_and_reprs_never_contain_challenges_or_results(self):
        _, outputs, challenge = self.start()
        safe = json.dumps(self.broker.status('phone-A'))
        self.assertNotIn(challenge['rand'], safe)
        self.assertNotIn(challenge['autn'], safe)
        self.assertNotIn(success(), safe)
        self.assertNotIn(challenge['rand'], repr(self.broker))
        self.assertNotIn(challenge['rand'], repr(self.broker._sessions['phone-A']))
        self.assertNotIn(challenge['rand'], repr(self.broker._sessions['phone-A'].challenge))
        self.submit(challenge)
        result = self.receive(outputs)
        self.assertNotIn(success(), repr(result))
        self.assertNotIn('payload', self.broker.status('phone-A'))
        self.assertNotIn('aka_verified', self.broker.status('phone-A'))
        self.assertIsNone(self.broker._sessions['phone-A'].challenge)
        result.clear()

    def test_two_paired_phones_are_independent(self):
        other = self.broker.begin('phone-B', 0)
        _, first, first_challenge = self.start()
        _, second, second_challenge = self.start(2, 'phone-B', other)
        self.assertNotEqual(first_challenge['challenge_id'], second_challenge['challenge_id'])
        self.assertError('UNKNOWN_CHALLENGE', self.broker.submit, 'phone-B', other['session_id'], {
            'challenge_id': first_challenge['challenge_id'], 'state': 'SUCCESS', 'payload': success()})
        self.submit(second_challenge, 'CARRIER_PRIVILEGE_REQUIRED', None, 'phone-B', other)
        self.assertEqual('CARRIER_PRIVILEGE_REQUIRED', self.receive(second).state)
        self.submit(first_challenge)
        self.assertEqual('SUCCESS', self.receive(first).state)


if __name__ == '__main__':
    unittest.main()

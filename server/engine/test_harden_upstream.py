import ast
import contextlib
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import harden_upstream as h


FIXTURE = '''
from CryptoMobile.Milenage import Milenage
DEFAULT_IMSI = '123456012345678'
DEFAULT_RES = 'deadbeef'
DEFAULT_CK = 'secret'
DEFAULT_IK = 'secret'
if os.environ.get('SWU_APDU_DEBUG'):
    CardConnection.transmit = evil
def swu_write_status(state, **extra):
    open('secret-status', 'w').write(str(extra))
def return_imsi(interface):
    return DEFAULT_IMSI
def return_res_ck_ik(interface, rand, autn, ki, op, opc):
    return DEFAULT_RES, DEFAULT_CK, DEFAULT_IK
def read_res_ck_ik(reader, rand, autn):
    return 'physical', None, None, None
def return_auts(rand, autn, ki, op, opc, sqn):
    return Milenage(op).f1star(ki)
def diagnostics(secret):
    print(secret())
    swu_write_status('AUTH', value=secret())
    logging.error(secret())
def options(parser):
    parser.add_option('--ki', dest='ki')
    parser.add_option('--sqn', dest='sqn')
def response(manager):
    manager.send_action({'Action': 'AuthResponse', 'Registration': 'x'})
if __name__ == '__main__':
    execute_gateway()
'''


def isolated(source, ami=False):
    tree = ast.parse(h.patch_source(source, ami))
    # Never import/execute the gateway module: only isolated boundary functions.
    wanted = {'return_imsi', 'return_res_ck_ik', 'read_res_ck_ik', '_nexvary_vector', 'diagnostics', 'swu_write_status', 'response', 'return_auts'}
    defs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    namespace = {}
    exec(compile(ast.Module(body=defs, type_ignores=[]), '<isolated-boundary>', 'exec'), namespace)
    return namespace


class HardenTests(unittest.TestCase):
    def setUp(self):
        self.backend = types.SimpleNamespace(
            identity=lambda: '234150123456789',
            authenticate=lambda r, a: ('aa' * 8, 'bb' * 16, 'cc' * 16),
            authenticate_ami=lambda r, a: ('aa' * 8, 'bb' * 16, 'cc' * 16, None))
        self.module = types.SimpleNamespace(get_backend=lambda: self.backend)
        self.modules = patch.dict(sys.modules, {'nexvary_aka_backend': self.module})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_normal_vector_and_real_identity(self):
        funcs = isolated(FIXTURE)
        self.assertEqual(funcs['return_imsi']('ignored'), '234150123456789')
        self.assertEqual(funcs['return_res_ck_ik']('ignored', 'rand', 'autn'), self.backend.authenticate('', ''))
        self.assertEqual(isolated(FIXTURE, True)['read_res_ck_ik']('ignored', '', ''), self.backend.authenticate_ami('', ''))

    def test_sync_contract_matches_both_actual_consumers(self):
        self.backend.authenticate = lambda r, a: ('dd' * 14, None, None)
        self.backend.authenticate_ami = lambda r, a: (None, None, None, 'dd' * 14)
        self.assertEqual(isolated(FIXTURE)['return_res_ck_ik']('', '', ''), ('dd' * 14, None, None))
        self.assertEqual(isolated(FIXTURE, True)['read_res_ck_ik']('', '', ''), (None, None, None, 'dd' * 14))

    def test_unavailable_and_invalid_results_fail_closed_without_secret_logs(self):
        funcs = isolated(FIXTURE)
        for value in [(None, None, None), ('bad', 'bb'*16, 'cc'*16), ('aa'*8, 'bb', 'cc'*16), ('aa'*8, None, 'cc'*16), (None, 'dd'*14, None), ['aa'*8, 'bb'*16, 'cc'*16]]:
            self.backend.authenticate = lambda r, a, v=value: v
            with self.assertRaisesRegex(RuntimeError, '^Authentication unavailable$'):
                funcs['return_res_ck_ik']('', '', '')
        def fail(*args):
            raise ValueError('PRIVATE TOKEN CK IK IMSI')
        self.backend.authenticate = fail
        self.backend.identity = fail
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            for name, args in [('return_imsi', ('',)), ('return_res_ck_ik', ('', '', ''))]:
                with self.assertRaises(RuntimeError) as caught:
                    funcs[name](*args)
                self.assertNotIn('PRIVATE', str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(output.getvalue(), '')

    def test_longterm_credentials_rejected_before_backend(self):
        funcs = isolated(FIXTURE)
        for index in range(3):
            credentials = [None, None, None]
            credentials[index] = 'SECRET'
            with self.assertRaisesRegex(RuntimeError, 'Long-term credentials prohibited'):
                funcs['return_res_ck_ik']('', '', '', *credentials)
        with self.assertRaisesRegex(RuntimeError, 'Legacy authentication disabled'):
            funcs['return_auts']('', '', '', '', '', '')

    def test_diagnostic_arguments_never_evaluated_and_no_empty_authresponse(self):
        funcs = isolated(FIXTURE)
        def secret():
            self.fail('Secret diagnostic argument was evaluated')
        funcs['diagnostics'](secret)
        with self.assertRaisesRegex(RuntimeError, 'Authentication unavailable'):
            funcs['response'](object())
        tree = ast.parse(h.patch_source(FIXTURE))
        self.assertFalse(any(isinstance(n, ast.ImportFrom) and 'Milenage' in (n.module or '') for n in ast.walk(tree)))
        self.assertFalse(any(isinstance(n, ast.Constant) and n.value in {'SWU_APDU_DEBUG', '--ki', '--sqn', '123456012345678', 'deadbeef'} for n in ast.walk(tree)))
        gate = tree.body[-1]
        self.assertIsInstance(gate.body[0], ast.Raise)

    def test_staging_refuses_existing_and_wrong_revision_without_writing(self):
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / 'source'; src.mkdir()
            target = Path(root) / 'stage'
            with patch.object(h, '_git', return_value=b'wrong\n'):
                with self.assertRaisesRegex(ValueError, 'Wrong upstream revision'):
                    h.stage(src, target)
            self.assertFalse(target.exists())
            target.mkdir()
            with self.assertRaisesRegex(ValueError, 'fresh'):
                h.stage(src, target)

    def test_staging_refuses_dirty_source(self):
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / 'source'; src.mkdir()
            target = Path(root) / 'stage'
            with patch.object(h, '_git', side_effect=[h.PIN.encode(), b'?? private.env']):
                with self.assertRaisesRegex(ValueError, 'clean'):
                    h.stage(src, target)
            self.assertFalse(target.exists())

    def test_stage_copies_only_verified_files_with_no_executable_bit(self):
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / 'source'; (src / 'engine').mkdir(parents=True)
            hashes = {}
            for name in ('swu_ike.py', 'ami_usim.py'):
                rel = 'engine/' + name
                (src / rel).write_text(FIXTURE)
                hashes[rel] = hashlib.sha256((src / rel).read_bytes()).hexdigest()
            target = Path(root) / 'stage'
            files = ('\0'.join(hashes) + '\0').encode()
            with patch.object(h, 'HASHES', hashes), patch.object(h, '_git', side_effect=[h.PIN.encode(), b'', files]):
                h.stage(src, target)
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            for rel in hashes:
                self.assertEqual((target / rel).stat().st_mode & 0o777, 0o600)
                ast.parse((target / rel).read_text())
            self.assertTrue((target / '.nexvary-audit-stage').is_file())
            self.assertIn('"execution_reviewed": false', (target / 'NEXVARY-AUDIT.json').read_text())
            self.assertEqual((src / 'engine/swu_ike.py').read_text(), FIXTURE)

    def test_symlink_source_rejected_before_destination_creation(self):
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / 'source'; src.mkdir()
            (src / 'unsafe').symlink_to('/etc/passwd')
            target = Path(root) / 'stage'
            with patch.object(h, '_git', side_effect=[h.PIN.encode(), b'', b'unsafe\0']):
                with self.assertRaisesRegex(ValueError, 'regular tracked files'):
                    h.stage(src, target)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()

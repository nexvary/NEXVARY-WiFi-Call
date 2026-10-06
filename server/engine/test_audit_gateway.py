import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_gateway as scanner


FIXTURE = '''
import os, socket, subprocess
from cryptography.hazmat.primitives import hashes
from Crypto.Cipher import AES
class swu:
    def set_routes(self):
        subprocess.call('PRIVATE_COMMAND_AND_SIM_IDENTITY', shell=True)
        open('/private/config', 'w').write('PRIVATE_SECRET')
    def delete_routes(self):
        subprocess.call(['ip', 'route', 'del'], shell=False)
    def open_tun(self):
        return os.open('/dev/net/tun', os.O_RDWR)
    def exec_in_netns(self):
        subprocess.call('do not run', shell=True)
    def create_socket_esp(self):
        return socket.socket(socket.AF_INET, socket.SOCK_RAW)
raise RuntimeError('UPSTREAM_EXECUTED')
'''


class AuditTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        (root / '.git').mkdir(parents=True, exist_ok=True)
        hashes = {}
        for name in scanner.HASHES:
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
            content = FIXTURE if name.endswith('.py') else 'fixture MIT notice or nonexecuted build script\n'
            path.write_text(content)
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return root, hashes

    def test_ast_detects_actual_mutating_calls_without_evaluating_source_or_leaking_arguments(self):
        result = scanner.inventory(FIXTURE)
        sites = result['mutation_sites']
        self.assertEqual(['Crypto', 'cryptography', 'os', 'socket', 'subprocess'], result['import_roots'])
        self.assertTrue(any(s['function'] == 'swu.set_routes' and s['category'] == 'file_write_or_dynamic_mode' for s in sites))
        self.assertTrue(any(s['function'] == 'swu.create_socket_esp' and s['category'] == 'network_socket' for s in sites))
        self.assertTrue(any(s['function'] == 'swu.set_routes' and s['shell'] for s in sites))
        self.assertFalse(next(s for s in sites if s['function'] == 'swu.delete_routes')['shell'])
        serialized = json.dumps(result)
        for secret in ('PRIVATE_SECRET', 'PRIVATE_COMMAND_AND_SIM_IDENTITY', '/private/config', 'UPSTREAM_EXECUTED'):
            self.assertNotIn(secret, serialized)

    def test_verified_inventory_keeps_execution_blocked_and_files_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root, hashes = self.fixture(directory)
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(scanner, 'HASHES', hashes), patch.object(scanner, '_git', side_effect=[scanner.PIN.encode(), b'']):
                result = scanner.audit(root)
            after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertTrue(result['integrity_verified'])
            self.assertFalse(result['executable'])
            self.assertFalse(result['gateway_verified'])
            self.assertGreaterEqual(len(result['blockers']), 8)
            self.assertFalse(result['minimal_swu_only_candidate']['resource_verification'])
            self.assertIn('not an install manifest', result['minimal_swu_only_candidate']['status'])
            json.dumps(result)

    def test_wrong_revision_or_dirty_source_fails_before_file_access(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / '.git').mkdir()
            for output in ([b'wrong'], [scanner.PIN.encode(), b'?? private-secret.env']):
                with patch.object(scanner, '_git', side_effect=output), self.assertRaises(scanner.AuditRefused) as caught:
                    scanner.audit(directory)
                self.assertNotIn('secret', str(caught.exception))

    def test_tampered_license_or_source_rejected_even_if_git_reports_clean(self):
        for relative in ('LICENSE', 'engine/swu_ike.py', 'engine/entrypoint.sh'):
            with tempfile.TemporaryDirectory() as directory:
                root, hashes = self.fixture(directory)
                (root / relative).write_text('altered credential PRIVATE_SECRET')
                with patch.object(scanner, 'HASHES', hashes), patch.object(scanner, '_git', side_effect=[scanner.PIN.encode(), b'']), self.assertRaises(scanner.AuditRefused):
                    scanner.audit(root)

    def test_symlink_source_components_and_files_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root, hashes = self.fixture(Path(directory) / 'source')
            link = Path(directory) / 'link'; link.symlink_to(root)
            with self.assertRaises(scanner.AuditRefused): scanner.audit(link)
            (root / 'LICENSE').unlink(); (root / 'LICENSE').symlink_to('/etc/passwd')
            with patch.object(scanner, 'HASHES', hashes), patch.object(scanner, '_git', side_effect=[scanner.PIN.encode(), b'']), self.assertRaises(scanner.AuditRefused):
                scanner.audit(root)

    def test_verified_hash_cannot_hide_unexpected_missing_mutation_structure(self):
        with tempfile.TemporaryDirectory() as directory:
            root, hashes = self.fixture(directory)
            path = root / 'engine/swu_ike.py'; path.write_text('import os\n')
            hashes['engine/swu_ike.py'] = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(scanner, 'HASHES', hashes), patch.object(scanner, '_git', side_effect=[scanner.PIN.encode(), b'']), self.assertRaises(scanner.AuditRefused):
                scanner.audit(root)

    def test_dynamic_open_mode_flagged_but_readonly_file_not_mutation(self):
        result = scanner.inventory("def sample(mode):\n    open('private', mode)\n    open('readonly')\n    open('readonly', 'rb')\n")
        self.assertEqual(1, len(result['mutation_sites']))
        self.assertEqual('file_write_or_dynamic_mode', result['mutation_sites'][0]['category'])
        self.assertIn('indirect/aliased', result['completeness'])

    def test_path_and_stream_write_methods_are_flagged_without_exporting_private_values(self):
        result = scanner.inventory("def writer(path, stream):\n    path.write_text('PRIVATE_TEXT')\n    path.write_bytes(b'PRIVATE_BYTES')\n    stream.write('PRIVATE_STREAM')\n")
        self.assertEqual(['potential_path_write_method', 'potential_path_write_method', 'potential_stream_write_method'],
                         [item['category'] for item in result['mutation_sites']])
        self.assertNotIn('PRIVATE_', json.dumps(result))

    def test_git_disables_fsmonitor_helper_and_optional_index_writes(self):
        with patch.object(scanner.subprocess, 'check_output', return_value=b'result') as command:
            self.assertEqual(b'result', scanner._git('/fixture', 'status', '--porcelain'))
        arguments = command.call_args.args[0]
        self.assertEqual(['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-C', '/fixture', 'status', '--porcelain'], arguments)
        self.assertEqual(10, command.call_args.kwargs['timeout'])

    def test_git_file_or_symlink_refused_without_invoking_git(self):
        for linked in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / '.git'
                if linked: path.symlink_to('/tmp')
                else: path.write_text('gitdir: /elsewhere')
                with patch.object(scanner, '_git') as command, self.assertRaises(scanner.AuditRefused):
                    scanner.audit(directory)
                command.assert_not_called()


if __name__ == '__main__':
    unittest.main()

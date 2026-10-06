import json
import os
import unittest
from unittest.mock import patch

import isolation_probe as probe


class IsolationProbeTests(unittest.TestCase):
    def state(self):
        return {'-4routes': [], '-6routes': [], '-4rules': [], '-6rules': [],
                'dns': 'private-digest', 'namespaces': {'net': 'n', 'mnt': 'm', 'pid': 'p'}}

    def test_default_plan_never_starts_subprocess_or_reads_host_state(self):
        with patch('sys.argv', ['isolation_probe.py']), patch.object(probe, 'command') as command, \
                patch.object(probe, 'inventory') as inventory, patch('builtins.print') as output:
            probe.main()
        command.assert_not_called(); inventory.assert_not_called()
        self.assertTrue(json.loads(output.call_args.args[0])['plan_only'])

    def test_missing_privilege_or_tool_fails_before_mutation(self):
        with patch.object(os, 'geteuid', return_value=1000), patch.object(probe, 'command') as command:
            with self.assertRaises(RuntimeError): probe.probe()
            command.assert_not_called()
        with patch.object(os, 'geteuid', return_value=0), patch.object(probe.shutil, 'which', return_value=None), \
                patch.object(probe, 'inventory') as inventory:
            with self.assertRaises(RuntimeError): probe.probe()
            inventory.assert_not_called()

    def test_namespace_check_rejects_shared_host_before_mount(self):
        state = self.state()
        with patch.object(probe, 'inventory', return_value=state), patch.object(probe, 'command') as command:
            with self.assertRaises(RuntimeError): probe.child(state['namespaces'], '/unused/private/resolver')
            command.assert_not_called()

    def test_probe_uses_full_namespaces_private_propagation_and_verifies_host(self):
        state = self.state()
        output = {'network_isolated': True, 'mount_isolated': True, 'pid_isolated': True,
                  'dns_write_private': True, 'host_loopback_unreachable': True}
        with patch.object(os, 'geteuid', return_value=0), patch.object(probe.shutil, 'which', return_value='/tool'), \
                patch.object(probe, 'inventory', side_effect=[state, dict(state)]), \
                patch.object(probe, 'command', return_value=json.dumps(output).encode()) as command:
            result = probe.probe()
        args = command.call_args.args[0]
        for flag in ('--net', '--mount', '--pid', '--fork', '--kill-child=SIGKILL', '--mount-proc'):
            self.assertIn(flag, args)
        self.assertEqual(args[args.index('--propagation') + 1], 'private')
        self.assertTrue(result['host_state_unchanged']); self.assertFalse(result['gateway_started'])
        self.assertFalse(result['carrier_authentication_verified'])

    def test_host_change_and_failed_child_cannot_be_reported_as_success(self):
        state = self.state(); changed = dict(state, dns='different')
        for failure in (False, True):
            with self.subTest(child_failed=failure), patch.object(os, 'geteuid', return_value=0), \
                    patch.object(probe.shutil, 'which', return_value='/tool'), \
                    patch.object(probe, 'inventory', side_effect=[state, changed]), \
                    patch.object(probe, 'command', side_effect=RuntimeError('child failed') if failure else None, return_value=b'{}'):
                with self.assertRaisesRegex(RuntimeError, 'Host routes'): probe.probe()

    def test_time_dependent_kernel_fields_do_not_hide_real_route_changes(self):
        a = [{'dst': 'route', 'gateway': 'gateway', 'expires': 99}]
        b = [{'dst': 'route', 'gateway': 'gateway', 'expires': 98}]
        c = [{'dst': 'route', 'gateway': 'different', 'expires': 98}]
        self.assertEqual(probe.stable(a), probe.stable(b))
        self.assertNotEqual(probe.stable(a), probe.stable(c))


if __name__ == '__main__':
    unittest.main()

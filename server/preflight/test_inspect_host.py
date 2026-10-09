import unittest
from unittest.mock import patch
from inspect_host import CHECKS, deploy_plan, listening_ports, run

class InventoryTests(unittest.TestCase):
    def test_ipv4_ipv6_listener_conflicts(self):
        ports = listening_ports('tcp LISTEN 0 5 0.0.0.0:5061 0.0.0.0:*\nudp UNCONN 0 0 [::]:20001 [::]:*')
        self.assertEqual(ports, [5061, 20001])
    def test_incomplete_never_authorizes_deployment(self):
        p = deploy_plan({})
        self.assertFalse(p['automatic_deployment_allowed'])
        self.assertIn('incomplete_listeners', p['blockers'])
    def test_protected_services_and_port_conflict(self):
        p = deploy_plan({'services': {'status':'ok','output':'outline.service running\nnexvary-wifi-panel.service running'},
                         'listeners': {'status':'ok','output':'tcp LISTEN 0 0 *:8787 *:*'}})
        self.assertEqual(p['candidate_conflicting_ports'], [8787])
        self.assertEqual(len(p['protected_service_inventory']), 2)
    def test_fixed_command_inventory(self):
        for argv in CHECKS.values():
            self.assertNotIn('sudo', argv)
            self.assertFalse(any(x in argv for x in ('stop','restart','install','flush','--env','inspect')))
    @patch('inspect_host.shutil.which', return_value=None)
    def test_missing_not_success(self, _):
        self.assertEqual(run(['ss'])['status'], 'missing_tool')

if __name__ == '__main__': unittest.main()

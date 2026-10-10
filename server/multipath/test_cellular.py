import json
from pathlib import Path
import tempfile
import unittest
from decimal import Decimal
from multipath.calls import Calls, Route
from multipath.cellular import BudgetLedger, CellularController, candidate_config, read_manifest


class Pbx:
    def __init__(self, fail=False):
        self.fail = fail
        self.requests = []
    def request(self, *args):
        self.requests.append(args)
        if self.fail:
            raise RuntimeError("timeout")
        return {"id": "synthetic"}
    def hangup(self, call_id):
        self.requests.append(("hangup", call_id))
        if self.fail:
            raise RuntimeError("timeout")


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root/"trusted.json"
        self.manifest = {
            "schema": "nexvary.cellular-sip-gateway.v1", "gateway_id": "field-gateway",
            "owner": "a", "owner_extension": "1001", "trusted_admin_consent": True,
            "carrier_use_authorized": True, "gateway_side_limits_verified": True,
            "sip_tls_verified": True, "srtp_verified": True, "synthetic": False,
            "destinations": ["+201012345678"], "max_seconds": 120,
            "daily_budget": "4", "rate_per_minute": "1",
            "evidence": dict(online=True, sim_present=True, registered=True, voice_commands=True,
                             audio_interface=True, inbound_verified=True, outbound_verified=True,
                             two_way_audio_verified=True, verified_at=1000, firmware="lab-fixture"),
        }
        self.write()
    def tearDown(self):
        self.temp.cleanup()
    def write(self):
        self.path.write_text(json.dumps(self.manifest))
        self.path.chmod(0o600)
    def test_candidate_routes_are_exact_and_isolated(self):
        candidate_config(self.path, self.root/"candidate", 1000)
        config = (self.root/"candidate/cellular-extensions.conf").read_text()
        self.assertIn("PJSIP/+201012345678@cellular-field-gateway", config)
        self.assertNotIn("_X", config)
        self.assertNotIn("include =>", config)
        self.assertIn("[cellular-inbound-field-gateway]", config)
        self.assertEqual((self.root/"candidate/gateway-account.json").stat().st_mode & 0o777, 0o600)
    def test_simulated_stale_consent_and_injection_rejected(self):
        for field in ("trusted_admin_consent", "carrier_use_authorized", "gateway_side_limits_verified", "sip_tls_verified", "srtp_verified"):
            original = self.manifest[field]
            self.manifest[field] = False
            self.write()
            with self.assertRaises(PermissionError):
                read_manifest(self.path, 1000)
            self.manifest[field] = original
        self.manifest["synthetic"] = True
        self.write()
        with self.assertRaises(PermissionError):
            read_manifest(self.path, 1000)
        self.manifest["synthetic"] = False
        self.write()
        with self.assertRaises(PermissionError):
            read_manifest(self.path, 1400)
        self.manifest["gateway_id"] = "bad\ninclude=external"
        self.write()
        with self.assertRaises(ValueError):
            read_manifest(self.path, 1000)
    def test_durable_reservation_survives_restart_and_timeout(self):
        calls = Calls(lambda: 1000)
        ledger = BudgetLedger(self.root/"budget.sqlite")
        controller = CellularController(calls, Pbx(True), ledger, {"field-gateway": self.path})
        with self.assertRaises(RuntimeError):
            controller.originate("a", "+201012345678", "field-gateway")
        restarted = CellularController(Calls(lambda: 1001), Pbx(), BudgetLedger(self.root/"budget.sqlite"), {"field-gateway": self.path})
        with self.assertRaises(PermissionError):
            restarted.originate("a", "+201012345678", "field-gateway")
    def test_owner_and_destination_permissions(self):
        controller = CellularController(Calls(lambda: 1000), Pbx(), BudgetLedger(self.root/"budget.sqlite"), {"field-gateway": self.path})
        with self.assertRaises(PermissionError):
            controller.originate("b", "+201012345678", "field-gateway")
        with self.assertRaises(PermissionError):
            controller.originate("a", "+99999999999", "field-gateway")
        call = controller.originate("a", "+201012345678", "field-gateway")
        self.assertEqual(call.route, Route.CELLULAR)
        with self.assertRaises(PermissionError):
            controller.confirm_hangup("b", call.id)
        controller.confirm_hangup("a", call.id)
        call = controller.originate("a", "+201012345678", "field-gateway")
        controller.confirm_hangup("a", call.id)
        with self.assertRaises(PermissionError):
            controller.originate("a", "+201012345678", "field-gateway")

    def test_sim_removed_teardown_retried_and_budget_held(self):
        pbx = Pbx()
        controller = CellularController(Calls(lambda: 1000), pbx, BudgetLedger(self.root/"budget.sqlite"), {"field-gateway": self.path})
        call = controller.originate("a", "+201012345678", "field-gateway")
        self.manifest["evidence"]["sim_present"] = False
        self.write()
        pbx.fail = True
        controller.tick()
        self.assertIn(call.id, controller.pending_hangups)
        self.assertEqual(call.failure, "gateway_unavailable")
        pbx.fail = False
        controller.tick()
        self.assertNotIn(call.id, controller.pending_hangups)
        self.assertGreaterEqual(sum(r[0] == "hangup" for r in pbx.requests), 2)

    def test_private_manifest_parent_symlink_and_duplicate_keys(self):
        self.path.chmod(0o644)
        with self.assertRaises(PermissionError):
            read_manifest(self.path, 1000)
        self.path.chmod(0o600)
        self.root.chmod(0o755)
        with self.assertRaises(PermissionError):
            read_manifest(self.path, 1000)
        self.root.chmod(0o700)
        link = self.root/"manifest-link.json"
        link.symlink_to(self.path)
        with self.assertRaises(PermissionError):
            read_manifest(link, 1000)
        self.path.write_text('{"schema":"one","schema":"two"}')
        with self.assertRaises(ValueError):
            read_manifest(self.path, 1000)
        self.path.write_text(" "*16385)
        with self.assertRaises(PermissionError):
            read_manifest(self.path, 1000)

    def test_private_ledger_parent_and_symlink(self):
        self.root.chmod(0o755)
        with self.assertRaises(PermissionError):
            BudgetLedger(self.root/"new.sqlite")
        self.root.chmod(0o700)
        target = self.root/"target.sqlite"
        BudgetLedger(target)
        link = self.root/"db-link.sqlite"
        link.symlink_to(target)
        with self.assertRaises(PermissionError):
            BudgetLedger(link)
        target.chmod(0o644)
        with self.assertRaises(PermissionError):
            BudgetLedger(target)


if __name__ == "__main__":
    unittest.main()

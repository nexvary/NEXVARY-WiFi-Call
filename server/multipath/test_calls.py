import importlib.util
from pathlib import Path
import tempfile
import unittest
from decimal import Decimal
from multipath.calls import Calls, Policy, Route, State, VoiceEvidence
from multipath.asterisk import AriAdapter, InternalController


class Tests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.calls = Calls(lambda: self.now)
        self.calls.policies["a"] = Policy(frozenset({"1002"}), True, frozenset({"+201012345678"}),
                                         120, Decimal("4"), Decimal("1"))
        self.calls.gateways["g"] = VoiceEvidence("g", True, True, True, True, True, True, True, True,
                                                "observed", "field-test", self.now)

    def test_internal_not_sim_identity(self):
        call = self.calls.start("a", "1002", Route.INTERNAL, "g")
        self.assertIsNone(call.gateway)
        self.assertEqual(call.reservation, 0)
        with self.assertRaises(PermissionError):
            self.calls.start("a", "1002", Route.INTERNAL)

    def test_cost_reservation_and_bill(self):
        call = self.calls.start("a", "+201012345678", Route.CELLULAR, "g")
        self.assertEqual(call.reservation, 2)
        self.calls.transition(call.id, State.ACTIVE)
        self.now += 61
        self.calls.transition(call.id, State.ENDED)
        self.assertEqual(call.cost, 2)
        self.assertEqual(self.calls.spent[("a", 0)], 2)
        self.assertEqual(call.reservation, 0)

    def test_busy_and_unknown_modem(self):
        with self.assertRaises(PermissionError):
            self.calls.start("a", "+201012345678", Route.CELLULAR, "K3770")
        self.calls.start("a", "+201012345678", Route.CELLULAR, "g")
        self.calls.policies["b"] = self.calls.policies["a"]
        with self.assertRaises(PermissionError):
            self.calls.start("b", "+201012345678", Route.CELLULAR, "g")

    def test_no_premium_injection_emergency_or_carrier_fallback(self):
        for target in ("112", "911", "123", "+99999999999", "1002\nDial(SIP/a)"):
            with self.assertRaises(PermissionError):
                self.calls.start("a", target, Route.CELLULAR, "g")
        for route in (Route.CARRIER, Route.USB_USIM):
            with self.assertRaises(PermissionError):
                self.calls.start("a", "1002", route)

    def test_stale_and_disconnect(self):
        call = self.calls.start("a", "+201012345678", Route.CELLULAR, "g")
        self.calls.gateways["g"] = VoiceEvidence("g")
        self.assertEqual(self.calls.terminate_due(), [call.id])
        self.assertEqual(call.failure, "gateway_unavailable")
        self.assertEqual(call.reservation, 0)
        self.assertEqual(self.calls.terminate_due(), [])

    def test_duration_enforced_and_state_not_reopened(self):
        call = self.calls.start("a", "1002", Route.INTERNAL)
        self.now += 120
        self.assertEqual(self.calls.terminate_due(), [call.id])
        with self.assertRaises(ValueError):
            self.calls.transition(call.id, State.ACTIVE)

    def test_budget_denied(self):
        self.calls.spent[("a", 0)] = Decimal("3")
        with self.assertRaises(PermissionError):
            self.calls.start("a", "+201012345678", Route.CELLULAR, "g")

    def test_ari_untrusted_urls(self):
        for url in ("http://pbx.example/ari", "http://localhost/ari", "https://u:p@host/ari",
                    "https://host/ari?api_key=secret", "file:///ari"):
            with self.assertRaises(ValueError):
                AriAdapter(url, "user", "secret")

    def test_generated_pbx_private_deny_default(self):
        spec = importlib.util.spec_from_file_location("generate", Path(__file__).parents[1]/"deploy/pbx/generate.py")
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        with tempfile.TemporaryDirectory() as temp:
            out = generator.generate(Path(temp)/"pbx")
            pjsip = (out/"pjsip.conf").read_text()
            dialplan = (out/"extensions.conf").read_text()
            self.assertIn("media_encryption_optimistic=no", pjsip)
            self.assertNotIn("protocol=udp", pjsip)
            self.assertNotIn("_X", dialplan)
            self.assertNotIn("Dongle/", dialplan)
            self.assertEqual((out/"accounts.json").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                generator.generate(out)

    def test_invalid_policy_numeric(self):
        for amount in ("NaN", "Infinity", "-1"):
            with self.assertRaises(ValueError):
                Policy(frozenset({"1002"}), daily_budget=Decimal(amount))


if __name__ == "__main__":
    unittest.main()

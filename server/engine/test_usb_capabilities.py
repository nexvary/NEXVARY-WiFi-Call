import json
import os
import sys
import unittest
from pathlib import Path
from usb_capabilities import InvalidCapabilityReport, parse_usb_report

class UsbCapabilityTests(unittest.TestCase):
    def fixture(self):
        root = Path(os.environ.get('NEXVARY_USB_ROOT', Path(__file__).resolve().parents[3] / 'NEXVARY-USB'))
        sys.path.insert(0, str(root))
        from nexvary_usim_lab.core import Report, Reading
        from nexvary_usim_lab.wificall_capabilities import export_capabilities
        report = Report('NEXVARY USB Studio','0.8.1','2026-10-09T00:00:00Z','COM3',False,[Reading('Connection','OK','OK',''),Reading('Model','OK','K3770','')])
        return export_capabilities(report)
    def test_real_cross_repo_diagnostic_contract_is_not_authorization(self):
        parsed = parse_usb_report(json.dumps(self.fixture()).encode())
        self.assertFalse(parsed['calling_authorized'])
        self.assertFalse(parsed['trusted_attestation'])
        self.assertEqual(parsed['stages']['usim_aka']['state'], 'not_verified')
    def test_apdu_never_promotes_aka(self):
        p = self.fixture(); p['stages']['apdu']={'state':'observed','evidence':'fixed_select_mf_9000'}
        self.assertFalse(parse_usb_report(json.dumps(p).encode())['calling_authorized'])
    def test_forged_authorization_or_aka_rejected(self):
        p = self.fixture(); p['calling_authorized']=True
        with self.assertRaises(InvalidCapabilityReport): parse_usb_report(json.dumps(p).encode())
        p = self.fixture(); p['stages']['usim_aka']={'state':'observed','evidence':'not_tested'}
        with self.assertRaises(InvalidCapabilityReport): parse_usb_report(json.dumps(p).encode())
    def test_extra_secrets_and_duplicates_rejected(self):
        p=self.fixture();p['ki']='secret'
        with self.assertRaises(InvalidCapabilityReport):parse_usb_report(json.dumps(p).encode())
        with self.assertRaises(InvalidCapabilityReport):parse_usb_report(b'{"schema":"a","schema":"b"}')
    def test_simulation_cannot_be_observed(self):
        p=self.fixture();p['simulated']=True
        with self.assertRaises(InvalidCapabilityReport):parse_usb_report(json.dumps(p).encode())
    def test_oversize_rejected(self):
        with self.assertRaises(InvalidCapabilityReport):parse_usb_report(b'x'*16385)

if __name__ == '__main__': unittest.main()

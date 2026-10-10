import json,unittest,os,sys
from pathlib import Path
from virtual_sim_evidence import parse_reader_evidence,InvalidReaderEvidence
class EvidenceTests(unittest.TestCase):
    def report(self):return dict(schema='nexvary.virtual-sim.v1',version='0.10.0',simulated=True,scope='directory_read_only',direct_select_mf=True,ef_dir_read=True,usim_selected=True,pcsc_enumerated=True,aka_verified=False,calling_authorized=False,physical_atr_available=False,electrical_reset_available=False)
    def test_no_report_authorizes_gateway(self):
        result=parse_reader_evidence(json.dumps(self.report()).encode())
        self.assertFalse(result['trusted_attestation']);self.assertFalse(result['gateway_enabled'])
    def test_reject_forged_successes_and_scopes(self):
        for key in ('aka_verified','calling_authorized','physical_atr_available','electrical_reset_available'):
            data=self.report();data[key]=True
            with self.assertRaises(InvalidReaderEvidence):parse_reader_evidence(json.dumps(data).encode())
        data=self.report();data['scope']='raw_apdu'
        with self.assertRaises(InvalidReaderEvidence):parse_reader_evidence(json.dumps(data).encode())
    def test_invalid_types_duplicates_and_dependency(self):
        with self.assertRaises(InvalidReaderEvidence):parse_reader_evidence(b'{"schema":"a","schema":"b"}')
        data=self.report();data['direct_select_mf']=False
        with self.assertRaises(InvalidReaderEvidence):parse_reader_evidence(json.dumps(data).encode())
    def test_actual_usb_contract_when_provided(self):
        root=os.environ.get('NEXVARY_USB_ROOT')
        if not root:self.skipTest('Cross-repository USB source not supplied.')
        sys.path.insert(0,root)
        from nexvary_usim_lab.reader_diagnostics import reader_evidence
        from nexvary_usim_lab.core import Report
        from nexvary_usim_lab import __version__
        result=parse_reader_evidence(json.dumps(reader_evidence(Report('NEXVARY USB Studio',__version__,'synthetic','COM9',True,[]))).encode())
        self.assertFalse(result['calling_authorized'])

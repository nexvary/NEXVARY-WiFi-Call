import unittest
from unittest.mock import patch
from nexvary_usb_backend import UsbAkaBackend
from strongswan_card_adapter import StrongSwanCardAdapter

IDENTITY='0123456789012345@nai.epc.mnc001.mcc001.3gppnetwork.org'
class FixtureBackend(UsbAkaBackend):
    def __init__(self,result):self.result=result;self.calls=0
    def identity(self):return IDENTITY
    def authenticate_ami(self,*challenge):
        self.calls+=1
        if isinstance(self.result,Exception):raise self.result
        return self.result
class CallbackTests(unittest.TestCase):
    def test_key_order_and_res_length_match_native_contract(self):
        b=FixtureBackend(('11'*4,'22'*16,'33'*16,None));a=StrongSwanCardAdapter(b)
        self.assertEqual(a.get_quintuplet(IDENTITY,b'R'*16,b'A'*16),('SUCCESS',b'\x22'*16,b'\x33'*16,b'\x11'*4))
        self.assertEqual(b.calls,1);self.assertIsNone(a.resync(IDENTITY,b'R'*16))
    def test_sync_consumes_auts_without_new_auth(self):
        b=FixtureBackend((None,None,None,'44'*14));a=StrongSwanCardAdapter(b)
        self.assertEqual(a.get_quintuplet(IDENTITY,b'R'*16,b'A'*16)[0],'INVALID_STATE')
        self.assertEqual(a.resync(IDENTITY,b'R'*16),b'\x44'*14)
        self.assertIsNone(a.resync(IDENTITY,b'R'*16));self.assertEqual(b.calls,1)
    def test_failure_identity_and_expired_sync_fail_closed(self):
        b=FixtureBackend(RuntimeError('PRIVATE'));a=StrongSwanCardAdapter(b)
        self.assertEqual(a.get_quintuplet('wrong',b'R'*16,b'A'*16)[0],'FAILED');self.assertEqual(b.calls,0)
        self.assertEqual(a.get_quintuplet(IDENTITY,b'R'*16,b'A'*16)[0],'FAILED')
        self.assertNotIn('PRIVATE',repr(a))
        b.result=(None,None,None,'44'*14)
        with patch('strongswan_card_adapter.time.monotonic',return_value=1):a.get_quintuplet(IDENTITY,b'R'*16,b'A'*16)
        with patch('strongswan_card_adapter.time.monotonic',return_value=32):self.assertIsNone(a.resync(IDENTITY,b'R'*16))

"""Cross-repository actual mTLS roundtrip; USIM/AKA result is synthetic."""
import os,sys,unittest,json,tempfile,shutil,threading
from pathlib import Path
from unittest.mock import patch
from nexvary_aka_backend import get_backend,AkaUnavailable
ROOT=os.environ.get('NEXVARY_USB_ROOT')
@unittest.skipUnless(ROOT,'Requires pinned USB reference checkout')
class CrossRepositoryTests(unittest.TestCase):
    def test_engine_factory_to_usb_bridge_actual_mtls_and_wrong_scope(self):
        root=Path(ROOT).resolve();sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
        from test_secure_bridge import SyntheticBackend,pin,TOKEN,CERTS
        from nexvary_usim_lab.secure_bridge import PrivateUsimBridge
        backend=SyntheticBackend();bridge=PrivateUsimBridge(backend,str(CERTS/'server.pem'),str(CERTS/'server-key.pem'),str(CERTS/'ca.pem'),pin('client'))
        thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                base=Path(directory);config=dict(backend='usb',port=bridge.port,device_key='synthetic-modem',token=TOKEN,server_pin=pin('server'))
                for field,name in [('server_ca','ca.pem'),('client_cert','client.pem'),('client_key','client-key.pem')]:
                    dest=base/name;shutil.copyfile(CERTS/name,dest);dest.chmod(0o600);config[field]=str(dest)
                auth=base/'auth.json';auth.write_text(json.dumps(config));auth.chmod(0o600)
                with patch.dict(os.environ,{'NEXVARY_ENGINE_AUTH_FILE':str(auth)}):
                    self.assertEqual(('12'*4,'34'*16,'56'*16),get_backend().authenticate('11'*16,'22'*16))
                    self.assertEqual(1,backend.calls)
                    config['device_key']='other-modem';auth.write_text(json.dumps(config))
                    with self.assertRaises(AkaUnavailable):get_backend().authenticate('33'*16,'44'*16)
                    self.assertEqual(1,backend.calls)
        finally:bridge.stop();thread.join(2)

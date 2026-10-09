"""Engine selection and independent TLS-client contract with synthetic AKA only."""
import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from nexvary_aka_backend import get_backend,AkaUnavailable
from nexvary_usb_backend import UsbAkaBackend
class UsbEngineTests(unittest.TestCase):
    def test_usb_factory_is_explicit_and_phone_default_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config={'backend':'usb','port':12345,'device_key':'synthetic','token':'A'*40,'server_pin':'0'*64}
            for key in ('server_ca','client_cert','client_key'):
                path=root/key;path.write_text('synthetic');path.chmod(0o600);config[key]=str(path)
            auth=root/'auth.json';auth.write_text(json.dumps(config));auth.chmod(0o600)
            with patch.dict(os.environ,{'NEXVARY_ENGINE_AUTH_FILE':str(auth)}),patch('nexvary_usb_backend.ssl.create_default_context'):
                backend=get_backend();self.assertIsInstance(backend,UsbAkaBackend)
                with self.assertRaises(AkaUnavailable):backend.identity()
                self.assertNotIn(config['token'],repr(backend))
                config['identity']='0123456789012345@nai.epc.mnc001.mcc001.3gppnetwork.org';auth.write_text(json.dumps(config))
                self.assertEqual(config['identity'],get_backend().identity())
                Path(config['client_key']).chmod(0o644)
                with self.assertRaises(AkaUnavailable):get_backend()
    def test_invalid_usb_never_falls_back_to_phone(self):
        with tempfile.TemporaryDirectory() as directory:
            auth=Path(directory)/'auth';auth.write_text(json.dumps({'backend':'usb','token':'A'*40}));auth.chmod(0o600)
            with patch.dict(os.environ,{'NEXVARY_ENGINE_AUTH_FILE':str(auth)}),patch('nexvary_aka_backend.PhoneAkaBackend') as phone:
                with self.assertRaises(AkaUnavailable):get_backend()
                phone.assert_not_called()
    def test_invalid_identity_before_transport(self):
        with self.assertRaises(AkaUnavailable):UsbAkaBackend(identity='invented',port=1)

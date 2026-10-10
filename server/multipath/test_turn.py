import base64
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from multipath.turn import issue_credentials, read_secret, write_credentials


class Tests(unittest.TestCase):
    def setUp(self):
        self.secret = b"A"*64
    def issue(self, **kwargs):
        return issue_credentials(self.secret, "owner-1", host="turn.example", trusted_caller=True,
                                 consent=True, clock=lambda: 1000, **kwargs)
    def test_hmac_short_expiry_scope_and_no_shared_secret(self):
        data = self.issue(ttl=120)
        self.assertEqual(data["expires_at"], 1120)
        self.assertTrue(data["username"].startswith("1120:"))
        self.assertNotIn("owner-1", data["username"])
        self.assertNotIn(self.secret.decode(), json.dumps(data))
        self.assertEqual(data["password"], base64.b64encode(hmac.new(self.secret, data["username"].encode(), hashlib.sha1).digest()).decode())
        self.assertNotEqual(data["username"], self.issue()["username"])
    def test_trust_consent_and_ttl_required(self):
        for kwargs in ({"trusted_caller":False,"consent":True},{"trusted_caller":True,"consent":False}):
            with self.assertRaises(PermissionError):
                issue_credentials(self.secret,"owner",host="turn.example",**kwargs)
        for ttl in (0,29,301,True,1.5):
            with self.assertRaises(ValueError):
                self.issue(ttl=ttl)
        for owner in ("../admin","victim:1000","owner\nadmin"):
            with self.assertRaises(ValueError):
                issue_credentials(self.secret,owner,host="turn.example",trusted_caller=True,consent=True)
    def test_private_secret_and_no_credential_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"secret"
            path.write_bytes(self.secret)
            path.chmod(0o600)
            self.assertEqual(read_secret(path),self.secret)
            output=Path(temp)/"credentials.json"
            write_credentials(output,self.issue())
            self.assertEqual(output.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):
                write_credentials(output,self.issue())
            path.chmod(0o644)
            with self.assertRaises(PermissionError):
                read_secret(path)
            path.chmod(0o600)
            link=Path(temp)/"link"
            link.symlink_to(path)
            with self.assertRaises(PermissionError):
                read_secret(link)
    def test_closed_relay_config_and_explicit_private_exception(self):
        spec=importlib.util.spec_from_file_location("turn_generate",Path(__file__).parents[1]/"deploy/turn/generate.py")
        generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/"turn"
            with self.assertRaises(PermissionError):
                generator.generate(out,peers=["127.0.0.1"],verified_pbx=True)
            generator.generate(out,peers=["127.0.0.1"],verified_pbx=True,verified_private_peer=True)
            config=(out/"turnserver.conf").read_text()
            for required in ("no-udp\n","no-tcp\n","no-tcp-relay","no-cli","use-auth-secret","denied-peer-ip=0.0.0.0-255.255.255.255","allowed-peer-ip=127.0.0.1"):
                self.assertIn(required,config)
            self.assertNotIn("no-auth",config)
            self.assertEqual((out/"auth-secret").stat().st_mode&0o777,0o600)
            self.assertEqual(out.stat().st_mode&0o777,0o700)


if __name__ == "__main__": unittest.main()

"""Staging bridge for libsimaka card callbacks; not a loaded charon plugin.

Matches get_quintuplet/resync semantics from strongSwan's simaka_card.h.
Only a configured UsbAkaBackend is accepted. No raw APDU, long-term keys,
triplet emulation, pseudonym persistence, or fast reauthentication storage.
"""
import hmac
import threading
import time
from nexvary_usb_backend import UsbAkaBackend, LabError

class StrongSwanCardAdapter:
    def __init__(self, backend):
        if not isinstance(backend,UsbAkaBackend):raise LabError('Explicit USB broker backend required.')
        self.backend=backend
        self._lock=threading.Lock()
        self._sync=None
    def __repr__(self):return '<StrongSwanCardAdapter: staging, private transient state>'
    def _identity(self,identity):
        expected=self.backend.identity()
        if not isinstance(identity,str) or not hmac.compare_digest(identity,expected):
            raise LabError('Selected provisioned identity mismatch.')
    def get_quintuplet(self,identity,rand,autn):
        """Return (SUCCESS, CK, IK, RES), (INVALID_STATE, None...), or FAILED.

        RAND/AUTN are 16-byte native callback buffers. Exceptions are suppressed
        into FAILED; no credential, challenge or backend exception is logged.
        """
        with self._lock:
            self._sync=None
            try:
                self._identity(identity)
                if not isinstance(rand,bytes) or not isinstance(autn,bytes) or len(rand)!=16 or len(autn)!=16:
                    raise LabError('Invalid callback challenge.')
                res,ck,ik,auts=self.backend.authenticate_ami(rand.hex(),autn.hex())
                if auts is not None:
                    self._sync=(identity,rand,bytes.fromhex(auts),time.monotonic()+30)
                    return 'INVALID_STATE',None,None,None
                return 'SUCCESS',bytes.fromhex(ck),bytes.fromhex(ik),bytes.fromhex(res)
            except Exception:
                return 'FAILED',None,None,None
    def resync(self,identity,rand):
        """Consume cached AUTS once; never repeat AUTH to obtain it."""
        with self._lock:
            cached=self._sync;self._sync=None
            try:
                self._identity(identity)
                if cached is None or not isinstance(rand,bytes) or len(rand)!=16:return None
                owner,challenge,auts,expires=cached
                if owner!=identity or not hmac.compare_digest(challenge,rand) or time.monotonic()>=expires:return None
                return auts
            except Exception:return None
    def close(self):
        with self._lock:self._sync=None

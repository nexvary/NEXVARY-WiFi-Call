"""Independent USB Studio client: loopback mTLS tunnel, scoped short-lived consent.

Own NEXVARY implementation; no dependency on USB Studio's GUI or repository.
"""
import base64,hashlib,hmac,http.client,json,re,socket,ssl,threading,uuid
from nexvary_aka_backend import AkaUnavailable as LabError
PATH='/v1/usim/aka'
def _pin(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):raise LabError('Invalid TLS pin.')
    return value

def parse_aka(data):
    if len(data)==16 and data[:2]==b'\xdc\x0e': return None,None,None,data[2:].hex().upper()
    if len(data)>=2 and data[0]==0xdb:
        n=data[1]; a=2+n; b=a+17
        if 4<=n<=16 and len(data) in (n+36,n+45) and data[a]==16 and data[b]==16:
            if len(data)==n+45 and data[n+36]!=8:raise LabError('Invalid optional AKA field.')
            return data[2:a].hex().upper(),data[a+1:b].hex().upper(),data[b+1:b+17].hex().upper(),None
    raise LabError('Invalid AKA result structure.')

class BridgeUsimClient:
    """Same WiFi-Call backend call contract, via a provisioned loopback TLS tunnel."""
    def __init__(self,port,device_key,token,server_ca,client_cert,client_key,server_pin):
        if type(port) is not int or not 1<=port<=65535 or not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',token):
            raise LabError('Invalid private bridge configuration.')
        self.port=port;self.key=device_key;self.token=token;self.pin=_pin(server_pin)
        self.context=ssl.create_default_context(cafile=server_ca);self.context.minimum_version=ssl.TLSVersion.TLSv1_2
        self.context.load_cert_chain(client_cert,client_key)
    def __repr__(self):return '<BridgeUsimClient: private credentials>'
    def identity(self):raise LabError('Carrier identity is configured separately.')
    def authenticate_ami(self,rand,autn):
        import re
        if not all(isinstance(x,str) and re.fullmatch('[0-9A-Fa-f]{32}',x) for x in (rand,autn)):
            raise LabError('Invalid AKA challenge.')
        request_id=str(uuid.uuid4());connection=None;timer=None
        try:
            connection=http.client.HTTPSConnection('localhost',self.port,timeout=35,context=self.context)
            connection.connect()
            if not hmac.compare_digest(hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest(),self.pin):
                raise LabError('Private TLS peer pin mismatch.')
            tlswire=connection.sock
            def expire():
                try:tlswire.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            timer=threading.Timer(35,expire);timer.daemon=True;timer.start()
            body=json.dumps(dict(device_key=self.key,request_id=request_id,rand=rand,autn=autn))
            connection.request('POST',PATH,body,headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token})
            response=connection.getresponse();raw=response.read(4097)
            if response.status!=200 or response.getheader('Content-Type')!='application/json' or len(raw)>4096:raise LabError('Authorized modem authentication unavailable.')
            result=json.loads(raw)
            if set(result)!={'state','payload','request_id'} or result['request_id']!=request_id or result['state'] not in ('SUCCESS','SYNC_FAILURE'):
                raise LabError('Malformed private bridge response.')
            data=base64.b64decode(result['payload'],validate=True)
            if len(data)>128 or (result['state']=='SUCCESS' and data[:1]!=b'\xdb') or (result['state']=='SYNC_FAILURE' and data[:1]!=b'\xdc'):
                raise LabError('Malformed private AKA response.')
            return parse_aka(data)
        except LabError:raise
        except Exception:raise LabError('Private modem bridge unavailable; check pairing, certificates and consent.') from None
        finally:
            if timer:timer.cancel()
            if connection:connection.close()
    def authenticate(self,rand,autn):
        res,ck,ik,auts=self.authenticate_ami(rand,autn)
        return (auts,None,None) if auts is not None else (res,ck,ik)


class UsbAkaBackend(BridgeUsimClient):
    """Engine-selected USB client with optional owner-provisioned carrier NAI.

    Never reads IMSI from a diagnostic report or generates a subscriber identity.
    Identity is private configuration and must be authorized by the operator.
    """
    def __init__(self,identity=None,**kwargs):
        if identity is not None and (not isinstance(identity,str) or not re.fullmatch(r'[0-9]{1,16}@(?:[a-z0-9-]+\.)+[a-z0-9-]+',identity)):
            raise LabError('Invalid provisioned carrier identity.')
        self._identity=identity
        super().__init__(**kwargs)
    def identity(self):
        if self._identity is None:raise LabError('Provisioned carrier identity unavailable.')
        return self._identity

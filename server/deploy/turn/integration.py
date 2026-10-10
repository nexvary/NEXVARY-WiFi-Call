#!/usr/bin/env python3
"""Actual disposable coturn TLS/auth/allocation/UDP relay test, not field NAT."""
import argparse
import hashlib
import hmac
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import ssl
import struct
import threading
import time
from multipath.turn import issue_credentials, read_secret

MAGIC = 0x2112A442


def attribute(kind, value):
    return struct.pack("!HH", kind, len(value))+value+b"\0"*((-len(value)) % 4)


def message(kind, attrs, transaction=None, key=None):
    transaction = transaction or secrets.token_bytes(12)
    body = b"".join(attribute(k, v) for k, v in attrs)
    header = struct.pack("!HHI", kind, len(body)+(24 if key else 0), MAGIC)+transaction
    if key:
        body += attribute(0x0008, hmac.new(key, header+body, hashlib.sha1).digest())
    return header+body


def xor_address(host, port):
    value = int(ipaddress.IPv4Address(host)) ^ MAGIC
    return struct.pack("!BBHI", 0, 1, port ^ (MAGIC >> 16), value)


class Turn:
    def __init__(self, ca):
        context = ssl.create_default_context(cafile=ca)
        self.sock = context.wrap_socket(socket.create_connection(("127.0.0.1",5349),timeout=5),server_hostname="127.0.0.1")
        self.sock.settimeout(5)
        self.credentials, self.realm, self.nonce = None, None, None
    def receive(self):
        def read_exact(size):
            data=b""
            while len(data)<size:
                chunk=self.sock.recv(size-len(data))
                if not chunk: raise RuntimeError("TURN connection closed")
                data+=chunk
            return data
        header=read_exact(20)
        kind,length,cookie=struct.unpack("!HHI",header[:8])
        if cookie != MAGIC or length > 16384: raise RuntimeError("Invalid TURN response")
        raw=read_exact(length)
        attrs={}
        offset=0
        while offset<len(raw):
            k,n=struct.unpack("!HH",raw[offset:offset+4])
            attrs[k]=raw[offset+4:offset+4+n]
            offset+=4+((n+3)//4)*4
        return kind,attrs
    def authenticated(self,kind,attrs):
        credential=self.credentials
        key=hashlib.md5((credential["username"]+":"+self.realm+":"+credential["password"]).encode()).digest()
        self.sock.sendall(message(kind,attrs+[(0x0006,credential["username"].encode()),(0x0014,self.realm.encode()),(0x0015,self.nonce)],key=key))
        return self.receive()
    def allocate(self,credential):
        self.sock.sendall(message(0x0003,[(0x0019,b"\x11\0\0\0")]))
        kind,attrs=self.receive()
        if kind!=0x0113 or attrs.get(0x0009,b"\0"*4)[2:4]!=b"\x04\x01":
            raise RuntimeError("TURN must challenge unauthenticated allocation")
        self.credentials=credential
        self.realm=attrs[0x0014].decode()
        self.nonce=attrs[0x0015]
        return self.authenticated(0x0003,[(0x0019,b"\x11\0\0\0")])
    def close(self): self.sock.close()


def run(args):
    secret=read_secret(args.secret_file)
    issue=lambda clock=time.time: issue_credentials(secret,"disposable-owner",ttl=30,host="127.0.0.1",trusted_caller=True,consent=True,clock=clock)
    # Authentication rejection includes cryptographically wrong and already-expired
    # credentials on fresh connections, not a simulated status result.
    for credential in (dict(issue(),password="wrong-password"),issue(lambda:time.time()-60)):
        rejected=Turn(args.ca)
        try:
            kind,attrs=rejected.allocate(credential)
            if kind!=0x0113 or 0x0009 not in attrs: raise RuntimeError("TURN accepted unauthorized allocation")
        finally: rejected.close()
    client=Turn(args.ca)
    echo=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    echo.bind(("127.0.0.1",0)); echo.settimeout(.2)
    stop=threading.Event()
    def echo_loop():
        while not stop.is_set():
            try:
                payload,source=echo.recvfrom(2048)
                echo.sendto(payload,source)
            except socket.timeout: pass
    peer=threading.Thread(target=echo_loop,daemon=True);peer.start()
    try:
        kind,attrs=client.allocate(issue())
        if kind!=0x0103 or 0x0016 not in attrs: raise RuntimeError("TURN authenticated allocation failed")
        # Global denial must reject another loopback address not explicitly listed.
        kind,attrs=client.authenticated(0x0008,[(0x0012,xor_address("127.0.0.2",echo.getsockname()[1]))])
        if kind!=0x0118 or attrs.get(0x0009,b"\0"*4)[2:4]!=b"\x04\x03":
            raise RuntimeError("TURN peer allowlist did not reject forbidden peer")
        kind,_=client.authenticated(0x0008,[(0x0012,xor_address("127.0.0.1",echo.getsockname()[1]))])
        if kind!=0x0108: raise RuntimeError("TURN allowed PBX permission failed")
        payload=b"nexvary-turn-synthetic-"+secrets.token_bytes(16)
        client.sock.sendall(message(0x0016,[(0x0012,xor_address("127.0.0.1",echo.getsockname()[1])),(0x0013,payload)]))
        kind,attrs=client.receive()
        if kind!=0x0017 or attrs.get(0x0013)!=payload: raise RuntimeError("TURN bidirectional relayed payload failed")
        kind,_=client.authenticated(0x0004,[(0x000D,struct.pack("!I",0))])
        if kind!=0x0104: raise RuntimeError("TURN allocation release failed")
        evidence={"synthetic":True,"scope":"actual_coturn_tls_allocation_and_udp_relay",
                  "tls_certificate_verified":True,"authenticated_allocation":True,
                  "wrong_password_rejected":True,"expired_new_allocation_rejected":True,
                  "forbidden_peer_rejected":True,"udp_payload_relay_both_directions":True,
                  "allocation_released":True,"field_nat_verified":False,"android_turn_verified":False,
                  "cellular_verified":False}
        Path(args.evidence).write_text(json.dumps(evidence,indent=2)+"\n")
        print("Actual coturn allocation, authorization rejection, expiry and UDP relay passed.")
    finally:
        stop.set();peer.join(timeout=2);echo.close();client.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-file",required=True)
    parser.add_argument("--ca",required=True)
    parser.add_argument("--evidence",required=True)
    run(parser.parse_args())

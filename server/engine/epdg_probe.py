#!/usr/bin/env python3
"""One-shot, opt-in, unauthenticated ePDG IKE_SA_INIT reachability probe.

Independent implementation of RFC 7296 sections 3.1-3.4/3.9/3.10 using the
RFC 3526 section 3 group-14 mathematical parameter. Pinned upstream SWu
(e3719840b93961f933aab3dac8bd2641936e2bcc) reviewed for wire compatibility;
no upstream runtime/dependencies or system/network mutation code is imported.
No DNS, identity, AKA, key derivation, IPsec, IKE_AUTH or retransmission occurs.
An unauthenticated response cannot prove the responder's carrier identity.
"""
import argparse
import ipaddress
import json
import re
import secrets
import socket
import struct
import time

HOST = re.compile(r'epdg\.epc\.mnc[0-9]{3}\.mcc[0-9]{3}\.pub\.3gppnetwork\.org\Z', re.ASCII)
MAX_PACKET = 1024
GROUP14 = int(''.join('''
FFFFFFFF FFFFFFFF C90FDAA2 2168C234 C4C6628B 80DC1CD1
29024E08 8A67CC74 020BBEA6 3B139B22 514A0879 8E3404DD
EF9519B3 CD3A431B 302B0A6D F25F1437 4FE1356D 6D51C245
E485B576 625E7EC6 F44C42E9 A637ED6B 0BFF5CB6 F406B7ED
EE386BFB 5A899FA5 AE9F2411 7C4B1FE6 49286651 ECE45B3D
C2007CB8 A163BF05 98DA4836 1C55D39A 69163FA8 FD24CF5F
83655D23 DCA3AD96 1C62F356 208552BB 9ED52907 7096966D
670C354E 4ABC9804 F1746C08 CA18217C 32905E46 2E36CE3B
E39E772C 180E8603 9B2783A2 EC07A28F B5C55DF0 6F4C52C9
DE2BCBF6 95581718 3995497C EA956AE5 15D22618 98FA0510
15728E5A 8AACAA68 FFFFFFFF FFFFFFFF
'''.split()), 16)


def validate_target(host, address, timeout):
    if not isinstance(host, str) or HOST.fullmatch(host) is None:
        raise ValueError('A canonical 3GPP ePDG hostname is required.')
    try:
        parsed = ipaddress.ip_address(address)
    except (ValueError, TypeError):
        raise ValueError('A reviewed public IP address is required.') from None
    if not parsed.is_global or parsed.is_multicast or parsed.is_reserved or parsed.is_unspecified:
        raise ValueError('A reviewed public IP address is required.')
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 2 <= timeout <= 5:
        raise ValueError('Timeout must be between two and five seconds.')
    return str(parsed)


def _payload(next_type, body):
    return struct.pack('!BBH', next_type, 0, len(body)+4)+body


def proposal():
    transforms=[]
    for index, (kind, identifier, attribute) in enumerate(((1,12,struct.pack('!HH',0x800E,128)),(2,5,b''),(3,12,b''),(4,14,b''))):
        transforms.append(struct.pack('!BBHBBH',3 if index<3 else 0,0,8+len(attribute),kind,0,identifier)+attribute)
    body=b''.join(transforms)
    return struct.pack('!BBHBBBB',0,0,8+len(body),1,1,0,4)+body


def build_request():
    spi=secrets.token_bytes(8)
    while spi==b'\0'*8:
        spi=secrets.token_bytes(8)
    # A fresh 256-bit exponent exceeds group14's 224-bit security requirement.
    # No shared key is calculated or kept; Python cannot guarantee integer erasure.
    exponent=secrets.randbits(256) | (1<<255)
    public=pow(2,exponent,GROUP14).to_bytes(256,'big')
    exponent=None
    body=_payload(34,proposal())+_payload(40,struct.pack('!HH',14,0)+public)+_payload(0,secrets.token_bytes(32))
    packet=struct.pack('!8s8sBBBBII',spi,b'\0'*8,33,0x20,34,0x08,0,28+len(body))+body
    return spi,packet


def _selected_sa(body):
    if len(body)<8:
        raise ValueError('Invalid proposal.')
    last,reserved,length,number,protocol,spi_size,count=struct.unpack('!BBHBBBB',body[:8])
    if last!=0 or reserved!=0 or length!=len(body) or number!=1 or protocol!=1 or spi_size!=0 or count!=4:
        raise ValueError('Invalid proposal.')
    offset=8; selected={}
    for index in range(count):
        if offset+8>len(body):raise ValueError('Invalid transform.')
        next_type,reserved,length,kind,reserved2,identifier=struct.unpack('!BBHBBH',body[offset:offset+8])
        if next_type!=(3 if index<count-1 else 0) or reserved or reserved2 or length<8 or offset+length>len(body) or kind in selected:
            raise ValueError('Invalid transform.')
        attrs=body[offset+8:offset+length]
        if kind==1:
            if len(attrs)!=4 or struct.unpack('!HH',attrs)!=(0x800E,128):return False
        elif attrs:
            raise ValueError('Unsupported transform attributes.')
        selected[kind]=identifier
        offset+=length
    if offset!=len(body):raise ValueError('Invalid proposal boundary.')
    return selected=={1:12,2:5,3:12,4:14}


def parse_response(packet, spi):
    try:
        if not isinstance(packet,bytes) or not 28<len(packet)<=MAX_PACKET or len(spi)!=8:
            raise ValueError()
        initiator,responder,next_type,version,exchange,flags,message_id,length=struct.unpack('!8s8sBBBBII',packet[:28])
        if initiator!=spi or version!=0x20 or exchange!=34 or message_id!=0 or not flags&0x20 or flags&0x08 or length!=len(packet):
            raise ValueError()
        offset=28; bodies={}; notifications=[]; count=0
        while next_type:
            count+=1
            if count>16 or offset+4>len(packet):raise ValueError()
            kind=next_type
            next_type,flags,payload_length=struct.unpack('!BBH',packet[offset:offset+4])
            if payload_length<4 or offset+payload_length>len(packet):raise ValueError()
            body=packet[offset+4:offset+payload_length]
            if kind not in {33,34,38,40,41,43} and flags&0x80:raise ValueError()
            if kind in {33,34,40}:
                if kind in bodies:raise ValueError()
                bodies[kind]=body
            elif kind==41:
                if len(body)<4:raise ValueError()
                protocol,spi_size,code=struct.unpack('!BBH',body[:4])
                if protocol!=0 or spi_size!=0:raise ValueError()
                data=body[4:]
                if code==16390 and not 1<=len(data)<=64:raise ValueError()
                if code==17 and len(data)!=2:raise ValueError()
                if code==14 and data:raise ValueError()
                if code in {16388,16389} and len(data)!=20:raise ValueError()
                notifications.append(code)
            offset+=payload_length
        if offset!=len(packet):raise ValueError()
        selected=_selected_sa(bodies[33]) if 33 in bodies else False
        if 34 in bodies:
            body=bodies[34]
            if len(body)!=260 or body[:4]!=struct.pack('!HH',14,0):raise ValueError()
            peer=int.from_bytes(body[4:],'big')
            if not 2<=peer<=GROUP14-2 or pow(peer,(GROUP14-1)//2,GROUP14)!=1:raise ValueError()
        if 40 in bodies and not 16<=len(bodies[40])<=256:raise ValueError()
        complete=selected and {33,34,40}<=bodies.keys() and responder!=b'\0'*8
        if 16390 in notifications:category='cookie_requested';complete=False
        elif 17 in notifications:category='different_dh_requested';complete=False
        elif 14 in notifications:category='proposal_rejected';complete=False
        elif any(code<16384 for code in notifications):category='error_notify';complete=False
        elif complete:category='offered_proposal_ke_nonce_received'
        else:category='incomplete_or_unselected_response'
        return {'state':'ike_init_response_received','response_kind':category,'offered_proposal_selected':bool(complete),
                'notify_types':notifications,'peer_authenticated':False,'aka_verified':False,'ipsec_established':False,'ims_registered':False}
    except (ValueError,TypeError,struct.error,IndexError):
        raise ValueError('Invalid or uncorrelated IKE_SA_INIT response.') from None


def probe(host,address,timeout=5):
    address=validate_target(host,address,timeout)
    spi,packet=build_request()
    started=time.monotonic()
    packets_sent=0
    try:
        family=socket.AF_INET6 if ':' in address else socket.AF_INET
        with socket.socket(family,socket.SOCK_DGRAM) as transport:
            transport.settimeout(timeout)
            transport.connect((address,500))
            count=transport.send(packet)  # Exactly one datagram; no retransmit/IKE_AUTH.
            packets_sent=1
            if count!=len(packet):raise OSError()
            remaining=timeout-(time.monotonic()-started)
            if remaining<=0:raise TimeoutError()
            transport.settimeout(remaining)
            response=transport.recv(MAX_PACKET+1)
            result=parse_response(response,spi)
    except TimeoutError:
        result={'state':'no_response_within_deadline'}
    except OSError:
        result={'state':'udp_probe_unavailable'}
    except ValueError:
        result={'state':'invalid_or_uncorrelated_response'}
    result.update({'host':host,'address':address,'address_source':'operator_supplied','dns_verified':False,
                   'peer_authenticated':False,'aka_verified':False,'ipsec_established':False,'ims_registered':False,
                   'packets_sent':packets_sent,'packets_sent_maximum':1,'observed_at':int(time.time())})
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description='Plan-only by default; a single unauthenticated IKE_SA_INIT is opt-in.')
    parser.add_argument('--probe',action='store_true')
    parser.add_argument('--host',help='Canonical carrier ePDG hostname.')
    parser.add_argument('--address',help='Public IP independently resolved/reviewed by the operator; no DNS is performed.')
    parser.add_argument('--timeout',type=float,default=5)
    options=parser.parse_args(argv)
    if not options.probe:
        print(json.dumps({'state':'plan_only','packets_sent':0,'dns_performed':False,'authentication_performed':False,
                          'required':'Explicit --probe --host canonical-ePDG --address reviewed-public-IP','ipsec_established':False}))
        return
    try:result=probe(options.host,options.address,options.timeout)
    except ValueError:raise SystemExit('Invalid probe target or timeout.') from None
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()

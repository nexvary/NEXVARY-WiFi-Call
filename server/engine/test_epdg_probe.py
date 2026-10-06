"""Deterministic, synthetic IKE fixtures; no carrier endpoint is contacted."""
import contextlib
import io
import json
import socket
import struct
import unittest
from unittest.mock import patch

import epdg_probe as probe

SPI=b'S'*8
HOST='epdg.epc.mnc001.mcc602.pub.3gppnetwork.org'


def response(parts,responder=b'R'*8,flags=0x20):
    bodies=b''
    for index,(kind,body) in enumerate(parts):
        bodies+=probe._payload(parts[index+1][0] if index+1<len(parts) else 0,body)
    return struct.pack('!8s8sBBBBII',SPI,responder,parts[0][0],0x20,34,flags,0,28+len(bodies))+bodies


def complete():
    return response([(33,probe.proposal()),(34,struct.pack('!HH',14,0)+pow(2,17,probe.GROUP14).to_bytes(256,'big')),(40,b'N'*32)])


def notify(code,data=b''):
    return response([(41,struct.pack('!BBH',0,0,code)+data)],responder=b'\0'*8)


class EpdgProbeTests(unittest.TestCase):
    def assertUnverified(self,result):
        for name in ('peer_authenticated','aka_verified','ipsec_established','ims_registered'):
            self.assertIs(False,result[name])

    def test_default_plan_performs_no_dns_crypto_or_network(self):
        output=io.StringIO()
        with patch.object(probe.socket,'socket') as transport,patch.object(probe,'build_request') as build,patch.object(probe.socket,'getaddrinfo') as dns,contextlib.redirect_stdout(output):
            probe.main([])
        self.assertEqual('plan_only',json.loads(output.getvalue())['state'])
        transport.assert_not_called();build.assert_not_called();dns.assert_not_called()

    def test_targets_require_canonical_hostname_public_address_and_short_timeout(self):
        self.assertEqual('8.8.8.8',probe.validate_target(HOST,'8.8.8.8',5))
        self.assertEqual('2606:4700:4700::1111',probe.validate_target(HOST,'2606:4700:4700::1111',2))
        for address in ('127.0.0.1','10.0.0.1','169.254.1.1','224.0.0.1','::1','ff02::1','192.0.2.1','example.org'):
            with self.assertRaises(ValueError):probe.validate_target(HOST,address,5)
        for host in ('epdg.example.org',HOST+'.',HOST.upper(),'epdg.epc.mnc1.mcc602.pub.3gppnetwork.org'):
            with self.assertRaises(ValueError):probe.validate_target(host,'8.8.8.8',5)
        for timeout in (0,1,6,True,float('nan')):
            with self.assertRaises(ValueError):probe.validate_target(HOST,'8.8.8.8',timeout)

    def test_group14_and_generated_request_have_exact_rfc_wire_structure(self):
        self.assertEqual(2048,probe.GROUP14.bit_length())
        spi,packet=probe.build_request()
        first,second,np,version,exchange,flags,mid,length=struct.unpack('!8s8sBBBBII',packet[:28])
        self.assertEqual((spi,b'\0'*8,33,0x20,34,8,0,len(packet)),(first,second,np,version,exchange,flags,mid,length))
        self.assertEqual(376,len(packet))
        self.assertTrue(probe._selected_sa(packet[32:76]))
        self.assertEqual((40,0,264,14,0),struct.unpack('!BBHHH',packet[76:84]))
        self.assertTrue(2<=int.from_bytes(packet[84:340],'big')<=probe.GROUP14-2)
        self.assertEqual((0,0,36),struct.unpack('!BBH',packet[340:344]))
        other,other_packet=probe.build_request()
        self.assertNotEqual(spi,other)
        self.assertNotEqual(packet[344:],other_packet[344:])

    def test_complete_correlated_response_is_not_authenticated_or_ipsec(self):
        result=probe.parse_response(complete(),SPI)
        self.assertEqual('ike_init_response_received',result['state'])
        self.assertEqual('offered_proposal_ke_nonce_received',result['response_kind'])
        self.assertTrue(result['offered_proposal_selected'])
        self.assertUnverified(result)

    def test_cookie_invalid_ke_and_no_proposal_are_distinct_without_retries(self):
        for code,data,expected in ((16390,b'cookie','cookie_requested'),(17,struct.pack('!H',19),'different_dh_requested'),(14,b'','proposal_rejected')):
            result=probe.parse_response(notify(code,data),SPI)
            self.assertEqual(expected,result['response_kind'])
            self.assertFalse(result['offered_proposal_selected'])
            self.assertUnverified(result)
        for packet in (notify(16390),notify(17,b'x'),notify(14,b'extra')):
            with self.assertRaises(ValueError):probe.parse_response(packet,SPI)

    def test_incomplete_or_different_suite_never_selects_offered_proposal(self):
        result=probe.parse_response(response([(33,probe.proposal())]),SPI)
        self.assertFalse(result['offered_proposal_selected'])
        modified=bytearray(probe.proposal());modified[15]=13
        result=probe.parse_response(response([(33,bytes(modified)),(34,struct.pack('!HH',14,0)+pow(2,17,probe.GROUP14).to_bytes(256,'big')),(40,b'N'*32)]),SPI)
        self.assertFalse(result['offered_proposal_selected'])
        self.assertUnverified(result)
        zero=bytearray(complete());zero[8:16]=b'\0'*8
        self.assertFalse(probe.parse_response(bytes(zero),SPI)['offered_proposal_selected'])

    def test_wrong_spi_exchange_flags_id_lengths_and_truncation_reject(self):
        valid=complete()
        mutations=[]
        for offset,value in ((0,0),(17,0x10),(18,35),(19,8),(23,1),(27,0)):
            packet=bytearray(valid);packet[offset]=value;mutations.append(bytes(packet))
        mutations.extend([valid[:27],valid[:-1],valid+b'x',b'x'*1025])
        for packet in mutations:
            with self.assertRaises(ValueError):probe.parse_response(packet,SPI)

    def test_bad_payload_chains_duplicates_ke_nonce_and_critical_payload_reject(self):
        packets=[]
        original=complete()
        for offset,value in ((30,1),(31,3)):
            malformed=bytearray(original);malformed[offset]=value;packets.append(bytes(malformed))
        packets.extend([response([(40,b'N'*32),(40,b'N'*32)]),response([(34,struct.pack('!HH',14,0)+b'\0'*256)]),response([(40,b'N'*15)])])
        critical=bytearray(response([(99,b'x')]));critical[29]=0x80;packets.append(bytes(critical))
        for packet in packets:
            with self.assertRaises(ValueError):probe.parse_response(packet,SPI)

    def test_explicit_probe_sends_one_packet_no_dns_and_reports_only_correlated_response(self):
        with patch.object(probe,'build_request',return_value=(SPI,b'packet')),patch.object(probe.socket,'socket') as factory,patch.object(probe.socket,'getaddrinfo') as dns:
            transport=factory.return_value.__enter__.return_value
            transport.send.return_value=6
            transport.recv.return_value=notify(16390,b'cookie')
            result=probe.probe(HOST,'8.8.8.8',2)
        transport.connect.assert_called_once_with(('8.8.8.8',500))
        transport.send.assert_called_once_with(b'packet')
        transport.recv.assert_called_once_with(1025)
        dns.assert_not_called()
        self.assertEqual(1,result['packets_sent'])
        self.assertFalse(result['dns_verified'])
        self.assertUnverified(result)

    def test_timeout_and_socket_failure_do_not_claim_response_or_authentication(self):
        for failure,expected,count in ((TimeoutError(),'no_response_within_deadline',1),(OSError(),'udp_probe_unavailable',1)):
            with patch.object(probe,'build_request',return_value=(SPI,b'packet')),patch.object(probe.socket,'socket') as factory:
                transport=factory.return_value.__enter__.return_value
                transport.send.return_value=6;transport.recv.side_effect=failure
                result=probe.probe(HOST,'8.8.8.8',2)
            self.assertEqual(expected,result['state'])
            self.assertEqual(count,result['packets_sent'])
            self.assertUnverified(result)


if __name__=='__main__':unittest.main()

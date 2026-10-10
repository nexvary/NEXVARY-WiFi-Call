#!/usr/bin/env python3
"""Disposable Android emulator peer. No cellular, real NAT or acoustic proof.

Only this fixture maps the emulator host alias in PBX SDP to loopback. Private
SIP credentials/SDES keys never appear in output. Reuses the verified TLS and
digest framing from the independent two-client PBX integration test.
"""
import argparse
import base64
import json
import os
import re
import socket
import subprocess
import struct
import time
import uuid
from pathlib import Path
from pbx_integration import Client
import pylibsrtp


class EmulatorPeer(Client):
    def __init__(self, *args, **kwargs):
        self.response_codes = []
        self.response_header_names = set()
        self.request_method_counts = {}
        self.dialog_step = "registration"
        self.reader_finished = False
        self.media_dialogs = 1
        self.decrypted_packets = {"outgoing": None, "incoming": None}
        self.dtmf_events = []
        super().__init__(*args, **kwargs)

    def fresh_media_dialog(self):
        # Bind while the old socket still owns its port: the next dialog must
        # use a different UDP port, so delayed/queued packets from the first
        # dialog can never be authenticated against the second SDES context.
        # Authentication errors remain fatal; no packets are silently ignored.
        replacement = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            replacement.bind(("127.0.0.1", 0))
            replacement.settimeout(.1)
            if replacement.getsockname()[1] == self.rtp.getsockname()[1]:
                raise RuntimeError("RTP dialog port isolation failed")
        except Exception:
            replacement.close()
            raise
        previous = self.rtp
        self.rtp = replacement
        self.key = os.urandom(30)
        self.media_dialogs += 1
        previous.close()

    def read(self):
        try:
            return super().read()
        finally:
            self.reader_finished = True

    def next(self, predicate, timeout=10):
        def observe(message):
            # Values, request URI, SDP and reason phrases are never exported.
            status = re.match(r"^SIP/2.0 ([1-6][0-9]{2})\b", message[0])
            if status and len(self.response_codes) < 32:
                self.response_codes.append(int(status.group(1)))
                allowed = {"via", "from", "to", "call-id", "cseq", "contact",
                           "www-authenticate", "content-type", "content-length"}
                self.response_header_names.update(set(message[1]) & allowed)
            method = message[0].partition(" ")[0]
            if method in {"INVITE", "ACK", "BYE", "OPTIONS", "CANCEL", "NOTIFY"}:
                self.request_method_counts[method] = min(100, self.request_method_counts.get(method, 0)+1)
                if method == "OPTIONS":
                    self.okay(message)
            return predicate(message)
        return super().next(observe, timeout)

    def sdp(self):
        return super().sdp().replace('RTP/SAVP 0\r\n', 'RTP/SAVP 0 101\r\n').replace(
            'a=rtpmap:0 PCMU/8000\r\n',
            'a=rtpmap:0 PCMU/8000\r\na=rtpmap:101 telephone-event/8000\r\na=fmtp:101 0-16\r\n')

    def media(self, remote_sdp, result):
        # Android reaches its host at this alias; the host-side fixture uses
        # loopback. This is deliberately not evidence of deployed NAT traversal.
        remote_sdp = remote_sdp.replace("c=IN IP4 10.0.2.2", "c=IN IP4 127.0.0.1")
        host = re.search(r"(?m)^c=IN IP4 (\S+)", remote_sdp).group(1)
        port = int(re.search(r"(?m)^m=audio (\d+)", remote_sdp).group(1))
        remote_key = base64.b64decode(re.search(r"inline:([A-Za-z0-9+/=]+)", remote_sdp).group(1))
        outbound = pylibsrtp.Session(pylibsrtp.Policy(key=self.key, ssrc_type=pylibsrtp.Policy.SSRC_ANY_OUTBOUND))
        inbound = pylibsrtp.Session(pylibsrtp.Policy(key=remote_key, ssrc_type=pylibsrtp.Policy.SSRC_ANY_INBOUND))
        ssrc = int.from_bytes(os.urandom(4), "big")
        count = 0
        seen_events = set()
        sequence = 0
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            packet = struct.pack("!BBHII", 0x80, 0, sequence, sequence*160, ssrc)+b"\xff"*160
            self.rtp.sendto(outbound.protect(packet), (host, port))
            sequence += 1
            try:
                data, _ = self.rtp.recvfrom(2048)
                # Authenticate every packet before parsing its RTP payload.
                # Any SRTP authentication/replay error fails this fixture.
                decoded = inbound.unprotect(data)
                payload_type, payload, event_identity = rtp_payload(decoded)
                if payload_type == 0 and len(payload) >= 160:
                    count += 1
                elif payload_type == 101 and len(payload) >= 4:
                    event, flags, duration = struct.unpack('!BBH', payload[:4])
                    identity = event_identity+(event,)
                    if flags & 0x80 and duration > 0 and identity not in seen_events:
                        seen_events.add(identity)
                        self.dtmf_events.append(event)
            except socket.timeout:
                pass
            time.sleep(.02)
        result.append(count)

    def okay(self, request):
        _, headers, _ = request
        self.send("SIP/2.0 200 OK", {k: headers[k.lower()] for k in
                  ("Via", "From", "To", "Call-ID", "CSeq")})


def incoming_from_android(peer):
    peer.dialog_step = "await_outgoing_invite"
    invite = peer.next(lambda m: m[0].startswith("INVITE "), timeout=90)
    peer.response(invite, 180, "Ringing")
    peer.response(invite, 200, "OK", peer.sdp())
    peer.dialog_step = "await_outgoing_ack"
    peer.next(lambda m: m[0].startswith("ACK "), timeout=20)
    received = []
    peer.dialog_step = "outgoing_srtp"
    peer.media(invite[2], received)
    if not received or received[0] < 10:
        raise RuntimeError("Android outgoing encrypted media was not received")
    peer.decrypted_packets["outgoing"] = received[0]
    if peer.dtmf_events != [5, 10]:
        raise RuntimeError("Encrypted RFC4733 completed DTMF sequence was not verified")
    peer.dialog_step = "await_outgoing_bye"
    peer.okay(peer.next(lambda m: m[0].startswith("BYE "), timeout=30))
    return received[0]


def outgoing_to_android(peer):
    peer.dialog_step = "await_incoming_answer"
    cid = uuid.uuid4().hex
    uri = f"sip:1001@{peer.host};transport=tls"
    headers = peer.headers("INVITE", "1001", cid, 1)
    headers["Content-Type"] = "application/sdp"
    peer.send("INVITE "+uri+" SIP/2.0", headers, peer.sdp())
    response = peer.next(lambda m: m[0].startswith(("SIP/2.0 401", "SIP/2.0 200"))
                         and m[1].get("cseq") == "1 INVITE", timeout=30)
    cseq = 1
    if response[0].startswith("SIP/2.0 401"):
        ack = peer.headers("ACK", "1001", cid, 1)
        ack["To"] = response[1]["to"]
        peer.send("ACK "+uri+" SIP/2.0", ack)
        cseq = 2
        headers = peer.headers("INVITE", "1001", cid, cseq)
        headers["Authorization"] = peer.digest(response[1]["www-authenticate"], "INVITE", uri)
        headers["Content-Type"] = "application/sdp"
        peer.send("INVITE "+uri+" SIP/2.0", headers, peer.sdp())
        response = peer.next(lambda m: m[0].startswith("SIP/2.0 200")
                             and m[1].get("cseq") == "2 INVITE", timeout=40)
    contact = re.search(r"<([^>]+)>", response[1]["contact"]).group(1)
    ack = peer.headers("ACK", "1001", cid, cseq)
    ack["To"] = response[1]["to"]
    peer.send("ACK "+contact+" SIP/2.0", ack)
    received = []
    peer.dialog_step = "incoming_srtp"
    peer.media(response[2], received)
    if not received or received[0] < 10:
        raise RuntimeError("Android incoming encrypted media was not received")
    peer.decrypted_packets["incoming"] = received[0]
    peer.dialog_step = "await_incoming_bye"
    peer.okay(peer.next(lambda m: m[0].startswith("BYE "), timeout=30))
    return received[0]


def wait_android_ready():
    deadline = time.monotonic()+40
    while time.monotonic() < deadline:
        stage = subprocess.run(["adb", "shell", "cat",
            "/sdcard/Download/NEXVARY-SIP-E2E/stage.json"],
            capture_output=True, timeout=5, check=False)
        if stage.returncode == 0 and len(stage.stdout) < 1024:
            try:
                if json.loads(stage.stdout).get("ready_for_incoming") is True:
                    return
            except (ValueError, AttributeError):
                pass
        time.sleep(.25)
    raise TimeoutError("Android did not finish releasing its outgoing dialog")


def rtp_payload(packet):
    """Bounded authenticated RTP parsing, including CSRC/extension/padding."""
    if len(packet) < 12 or packet[0] >> 6 != 2:
        raise ValueError("Invalid authenticated RTP header")
    offset = 12+4*(packet[0] & 0x0f)
    if packet[0] & 0x10:
        if len(packet) < offset+4:
            raise ValueError("Invalid authenticated RTP extension")
        extension_words = struct.unpack('!H', packet[offset+2:offset+4])[0]
        offset += 4+4*extension_words
    end = len(packet)
    if packet[0] & 0x20:
        padding = packet[-1]
        if padding == 0 or padding > end-offset:
            raise ValueError("Invalid authenticated RTP padding")
        end -= padding
    if offset > end:
        raise ValueError("Invalid authenticated RTP payload offset")
    return packet[1] & 0x7f, packet[offset:end], struct.unpack('!II', packet[4:12])


def run(args):
    accounts = json.loads(Path(args.accounts).read_text())["accounts"]
    peer = EmulatorPeer("1002", accounts["1002"], "127.0.0.1", 5061, args.ca)
    phase = "registration"
    outgoing_packets = None
    try:
        peer.register()
        Path(args.ready).write_text("registered\n")
        phase = "android_outgoing"
        outgoing_packets = incoming_from_android(peer)
        phase = "android_dialog_release"
        wait_android_ready()
        peer.fresh_media_dialog()
        phase = "android_incoming"
        incoming = outgoing_to_android(peer)
        Path(args.output).write_text(json.dumps({
            "success": True, "synthetic": True, "android_emulator_tested": True,
            "physical_android_tested": False, "cellular_tested": False,
            "real_nat_tested": False, "emulator_host_alias_mapping": True,
            "tls_peer_certificate_verified": True, "digest_registration": True,
            "outgoing_answer_and_hangup": True, "incoming_answer_and_hangup": True,
            "fresh_rtp_socket_per_dialog": peer.media_dialogs == 2,
            "rfc4733_dtmf_sequence_verified": peer.dtmf_events == [5, 10],
            "expected_synthetic_dtmf_sequence": ["5", "*"],
            "decrypted_srtp_from_android_packets": {"outgoing": outgoing_packets, "incoming": incoming},
        }, indent=2)+"\n")
    except Exception as error:
        Path(args.output).write_text(json.dumps({"success": False,
            "synthetic": True, "completed_phase": phase,
            "error_class": type(error).__name__, "cellular_tested": False,
            "dialog_step": peer.dialog_step,
            "outgoing_answer_and_hangup": outgoing_packets is not None and outgoing_packets >= 10,
            "fresh_rtp_socket_per_dialog": peer.media_dialogs == 2,
            "rfc4733_dtmf_sequence_verified": peer.dtmf_events == [5, 10],
            "completed_dtmf_event_count": len(peer.dtmf_events),
            "incoming_answer_and_hangup": False,
            "decrypted_srtp_from_android_packets": peer.decrypted_packets,
            "sip_request_method_counts": peer.request_method_counts,
            "sip_response_codes": peer.response_codes,
            "sip_response_header_names": sorted(peer.response_header_names),
            "reader_error_class": peer.reader_error,
            "reader_finished": peer.reader_finished})+"\n")
        raise
    finally:
        peer.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("accounts", "ca", "ready", "output"):
        parser.add_argument("--"+name, required=True)
    run(parser.parse_args())

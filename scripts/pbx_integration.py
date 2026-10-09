#!/usr/bin/env python3
"""Real synthetic two-user SIP TLS/digest + bidirectional SRTP test.

Requires a disposable Asterisk running generated PBX configuration, trusted test
certificate and pylibsrtp. Not an Android test or a cellular field test.
Never run against production accounts. No secret or SDP body is printed.
"""
import argparse
import base64
import hashlib
import json
import os
import queue
import re
import socket
import ssl
import struct
import threading
import time
import uuid
import pylibsrtp


def parse(raw):
    head, _, body = raw.partition("\r\n\r\n")
    lines = head.split("\r\n")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()
    return lines[0], headers, body


class Client:
    def __init__(self, extension, password, host, port, ca):
        self.extension, self.password, self.host = extension, password, host
        self.port = port
        self.tag = uuid.uuid4().hex
        self.key = os.urandom(30)
        self.rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp.bind(("127.0.0.1", 0))
        self.rtp.settimeout(.1)
        context = ssl.create_default_context(cafile=ca)
        self.sock = context.wrap_socket(socket.create_connection((host, port), timeout=10), server_hostname=host)
        self.sock.settimeout(1)
        self.messages = queue.Queue()
        self.stop = threading.Event()
        self.reader_error = None
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        pending = b""
        try:
            while not self.stop.is_set():
                try:
                    chunk = self.sock.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    return
                pending += chunk
                if len(pending) > 1024*1024:
                    raise RuntimeError("Oversize SIP response")
                while b"\r\n\r\n" in pending:
                    if pending.startswith(b"\r\n\r\n"):
                        pending = pending[4:]
                        continue
                    head, body = pending.split(b"\r\n\r\n", 1)
                    match = re.search(rb"(?im)^Content-Length:\s*(\d+)", head)
                    length = int(match.group(1)) if match else 0
                    if len(body) < length:
                        break
                    size = len(head)+4+length
                    self.messages.put(parse(pending[:size].decode()))
                    pending = pending[size:]
        except (OSError, ValueError, RuntimeError) as exc:
            if not self.stop.is_set():
                self.reader_error = type(exc).__name__

    def send(self, start, headers, body=""):
        lines = [start]+[f"{k}: {v}" for k, v in headers.items()]
        lines += [f"Content-Length: {len(body.encode())}", "", body]
        self.sock.sendall("\r\n".join(lines).encode())

    def headers(self, method, target, call_id, cseq):
        return {
            "Via": f"SIP/2.0/TLS 127.0.0.1:{self.sock.getsockname()[1]};branch=z9hG4bK{uuid.uuid4().hex};rport",
            "Max-Forwards": "70", "From": f"<sip:{self.extension}@{self.host}>;tag={self.tag}",
            "To": f"<sip:{target}@{self.host}>", "Call-ID": call_id,
            "CSeq": f"{cseq} {method}",
            "Contact": f"<sip:{self.extension}@127.0.0.1:{self.sock.getsockname()[1]};transport=tls>",
        }

    def next(self, predicate, timeout=10):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            try:
                message = self.messages.get(timeout=.2)
            except queue.Empty:
                if self.reader_error:
                    raise RuntimeError("SIP reader failed: "+self.reader_error)
                continue
            if predicate(message):
                return message
        raise TimeoutError("Expected SIP message did not arrive")

    def digest(self, challenge, method, uri):
        values = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
        realm, nonce = values["realm"], values["nonce"]
        md5 = lambda value: hashlib.md5(value.encode()).hexdigest()
        ha1 = md5(f"{self.extension}:{realm}:{self.password}")
        ha2 = md5(f"{method}:{uri}")
        cnonce = uuid.uuid4().hex
        if "qop" in values:
            response = md5(f"{ha1}:{nonce}:00000001:{cnonce}:auth:{ha2}")
            extra = f',qop=auth,nc=00000001,cnonce="{cnonce}"'
        else:
            response = md5(f"{ha1}:{nonce}:{ha2}")
            extra = ""
        opaque = f',opaque="{values["opaque"]}"' if "opaque" in values else ""
        return f'Digest username="{self.extension}",realm="{realm}",nonce="{nonce}",uri="{uri}",response="{response}",algorithm=MD5'+extra+opaque

    def register(self):
        cid = uuid.uuid4().hex
        uri = f"sip:{self.host}"
        headers = self.headers("REGISTER", self.extension, cid, 1)
        headers["Expires"] = "120"
        self.send("REGISTER "+uri+" SIP/2.0", headers)
        _, challenge, _ = self.next(lambda m: m[0].startswith("SIP/2.0 401"))
        headers = self.headers("REGISTER", self.extension, cid, 2)
        headers["Expires"] = "120"
        headers["Authorization"] = self.digest(challenge["www-authenticate"], "REGISTER", uri)
        self.send("REGISTER "+uri+" SIP/2.0", headers)
        response = self.next(lambda m: m[0].startswith("SIP/2.0") and m[1].get("cseq") == "2 REGISTER")
        if not response[0].startswith("SIP/2.0 200"):
            raise RuntimeError("SIP authentication rejected")

    def sdp(self):
        return ("v=0\r\no=nexvary 1 1 IN IP4 127.0.0.1\r\ns=Synthetic test\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\n"
                f"m=audio {self.rtp.getsockname()[1]} RTP/SAVP 0\r\na=rtpmap:0 PCMU/8000\r\na=sendrecv\r\n"
                f"a=crypto:1 AES_CM_128_HMAC_SHA1_80 inline:{base64.b64encode(self.key).decode()}\r\n")

    def response(self, invite, code, reason, body=""):
        _, original, _ = invite
        headers = {key: original[key.lower()] for key in ("Via", "From", "To", "Call-ID", "CSeq")}
        headers["To"] = original["to"]+";tag="+self.tag
        headers["Contact"] = self.headers("INVITE", self.extension, "x", 1)["Contact"]
        if body:
            headers["Content-Type"] = "application/sdp"
        self.send(f"SIP/2.0 {code} {reason}", headers, body)

    def media(self, remote_sdp, result):
        host = re.search(r"(?m)^c=IN IP4 (\S+)", remote_sdp).group(1)
        port = int(re.search(r"(?m)^m=audio (\d+)", remote_sdp).group(1))
        remote_key = base64.b64decode(re.search(r"inline:([A-Za-z0-9+/=]+)", remote_sdp).group(1))
        outbound = pylibsrtp.Session(pylibsrtp.Policy(key=self.key, ssrc_type=pylibsrtp.Policy.SSRC_ANY_OUTBOUND))
        inbound = pylibsrtp.Session(pylibsrtp.Policy(key=remote_key, ssrc_type=pylibsrtp.Policy.SSRC_ANY_INBOUND))
        ssrc = int.from_bytes(os.urandom(4), "big")
        count = 0
        end = time.monotonic()+5
        sequence = 0
        while time.monotonic() < end:
            packet = struct.pack("!BBHII", 0x80, 0, sequence, sequence*160, ssrc)+b"\xff"*160
            self.rtp.sendto(outbound.protect(packet), (host, port))
            sequence += 1
            try:
                data, _ = self.rtp.recvfrom(2048)
                decoded = inbound.unprotect(data)
                if len(decoded) >= 172 and decoded[1] & 0x7f == 0:
                    count += 1
            except socket.timeout:
                pass
            time.sleep(.02)
        result.append(count)

    def close(self):
        self.stop.set()
        self.sock.close()
        self.rtp.close()
        self.reader.join(timeout=2)


def run(args):
    accounts = json.loads(open(args.accounts).read())["accounts"]
    clients = []
    try:
        rejected = Client("1001", "synthetic-wrong-password", args.host, args.port, args.ca)
        clients.append(rejected)
        try:
            rejected.register()
        except RuntimeError as error:
            if str(error) != "SIP authentication rejected":
                raise
        else:
            raise RuntimeError("PBX accepted an invalid password")
        rejected.close()
        clients.remove(rejected)
        for extension in ("1001", "1002"):
            client = Client(extension, accounts[extension], args.host, args.port, args.ca)
            clients.append(client)
            client.register()
        caller, callee = clients
        cid = uuid.uuid4().hex
        uri = f"sip:1002@{args.host};transport=tls"
        headers = caller.headers("INVITE", "1002", cid, 1)
        headers["Content-Type"] = "application/sdp"
        caller.send("INVITE "+uri+" SIP/2.0", headers, caller.sdp())
        _, challenge, _ = caller.next(lambda m: m[0].startswith("SIP/2.0 401"))
        ack = dict(headers)
        ack["CSeq"] = "1 ACK"
        ack["To"] = challenge["to"]
        caller.send("ACK "+uri+" SIP/2.0", ack)
        headers = caller.headers("INVITE", "1002", cid, 2)
        headers["Authorization"] = caller.digest(challenge["www-authenticate"], "INVITE", uri)
        headers["Content-Type"] = "application/sdp"
        caller.send("INVITE "+uri+" SIP/2.0", headers, caller.sdp())
        invite = callee.next(lambda m: m[0].startswith("INVITE "))
        callee.response(invite, 180, "Ringing")
        callee.response(invite, 200, "OK", callee.sdp())
        answer = caller.next(lambda m: m[0].startswith("SIP/2.0 200") and m[1].get("cseq") == "2 INVITE")
        ack = caller.headers("ACK", "1002", cid, 2)
        ack["To"] = answer[1]["to"]
        contact = re.search(r"<([^>]+)>", answer[1]["contact"]).group(1)
        caller.send("ACK "+contact+" SIP/2.0", ack)
        callee.next(lambda m: m[0].startswith("ACK "))
        received = [[], []]
        errors = []
        def media(client, sdp, result):
            try:
                client.media(sdp, result)
            except Exception as exc:
                errors.append(type(exc).__name__)
        threads = [threading.Thread(target=media, args=(caller, answer[2], received[0])),
                   threading.Thread(target=media, args=(callee, invite[2], received[1]))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        if errors or any(not counts or counts[0] < 10 for counts in received):
            raise RuntimeError("Bidirectional SRTP failed")
        bye = caller.headers("BYE", "1002", cid, 3)
        bye["To"] = answer[1]["to"]
        caller.send("BYE "+contact+" SIP/2.0", bye)
        incoming_bye = callee.next(lambda m: m[0].startswith("BYE "))
        # BYE responses retain dialog To tag; do not append a second tag.
        _, bh, _ = incoming_bye
        callee.send("SIP/2.0 200 OK", {k: bh[k.lower()] for k in ("Via", "From", "To", "Call-ID", "CSeq")})
        caller.next(lambda m: m[0].startswith("SIP/2.0 200") and m[1].get("cseq") == "3 BYE")
        print(json.dumps({"synthetic": True, "android_tested": False, "cellular_tested": False,
                          "tls": True, "digest_registration": True, "invalid_password_rejected": True, "incoming": True,
                          "outgoing": True, "hangup": True, "two_way_srtp_packets": [x[0] for x in received]}))
    finally:
        for client in clients:
            client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5061)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--accounts", required=True)
    run(parser.parse_args())

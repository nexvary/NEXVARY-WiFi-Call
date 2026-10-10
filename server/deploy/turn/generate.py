#!/usr/bin/env python3
"""Private opt-in coturn configuration. No service or firewall modifications."""
import argparse
import ipaddress
import os
from pathlib import Path
import re
import secrets


def generate(output, *, bind="127.0.0.1", relay_ip=None, realm="nexvary.invalid", peers=(),
             verified_pbx=False, verified_private_peer=False, min_port=24000, max_port=24031,
             external_ip=None):
    bind = str(ipaddress.IPv4Address(bind))
    relay_ip = str(ipaddress.IPv4Address(relay_ip or bind))
    if ipaddress.ip_address(relay_ip).is_unspecified:
        raise ValueError("Relay IP must be an actual dedicated interface, not wildcard")
    if external_ip:
        external_ip = str(ipaddress.IPv4Address(external_ip))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", realm):
        raise ValueError("Invalid provisioned TLS realm")
    if not verified_pbx or not peers or len(peers) > 8:
        raise PermissionError("Explicit verified PBX peer allowlist required")
    addresses = []
    loopback = False
    for peer in peers:
        address = ipaddress.ip_address(peer)
        if address.is_multicast or address.is_unspecified or address.is_link_local:
            raise PermissionError("Multicast, unspecified and link-local peers are forbidden")
        if not address.is_global and not verified_private_peer:
            raise PermissionError("Private/loopback peer needs explicit verified private PBX exception")
        loopback |= address.is_loopback
        addresses.append(str(address))
    if not 1024 <= min_port <= max_port <= 65535 or max_port-min_port > 255 or min_port <= 5349 <= max_port:
        raise ValueError("Use a bounded dedicated non-overlapping UDP relay port range")
    output = Path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    secret = secrets.token_urlsafe(48)
    config = f"""# Private NEXVARY TURN: exact verified PBX peer addresses only.
listening-ip={bind}
relay-ip={relay_ip}
tls-listening-port=5349
realm={realm}
server-name={realm}
use-auth-secret
static-auth-secret={secret}
cert=/etc/nexvary-turn/tls/fullchain.pem
pkey=/etc/nexvary-turn/tls/privkey.pem
no-udp
no-tcp
no-dtls
no-tlsv1
no-tlsv1_1
no-tcp-relay
no-cli
no-stun
no-multicast-peers
no-rfc5780
min-port={min_port}
max-port={max_port}
user-quota=2
total-quota=8
max-bps=128000
bps-capacity=1024000
stale-nonce=60
max-allocate-lifetime=300
fingerprint
no-software-attribute
denied-peer-ip=0.0.0.0-255.255.255.255
denied-peer-ip=::-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff
log-file=stdout
simple-log
pidfile=/run/nexvary-turn/turnserver.pid
"""
    if loopback:
        config += "allow-loopback-peers\n"  # Global deny + exact exceptions still apply.
    if external_ip:
        config += f"external-ip={external_ip}/{relay_ip}\n"
    config += "".join("allowed-peer-ip="+peer+"\n" for peer in addresses)
    for name, body in {"turnserver.conf": config, "auth-secret": secret+"\n"}.items():
        fd = os.open(output/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(body)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--relay-ip")
    parser.add_argument("--external-ip")
    parser.add_argument("--realm", required=True)
    parser.add_argument("--peer", action="append", required=True)
    parser.add_argument("--verified-pbx", action="store_true")
    parser.add_argument("--verified-private-peer", action="store_true")
    args = parser.parse_args()
    generate(args.output, bind=args.bind, relay_ip=args.relay_ip, realm=args.realm,
             peers=args.peer, verified_pbx=args.verified_pbx,
             verified_private_peer=args.verified_private_peer, external_ip=args.external_ip)
    print("Private TURN configuration generated; no listener or firewall change performed.")

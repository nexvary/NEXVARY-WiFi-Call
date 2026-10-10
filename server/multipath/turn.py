"""Short-lived TURN REST credentials, provisioned only by a trusted operator.

There is intentionally no public HTTP issuer. The shared coturn secret never
appears in returned client data, log messages or command-line arguments.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time


def read_secret(path):
    path = os.path.abspath(path)
    if os.path.realpath(path) != path:
        raise PermissionError("TURN secret path must not contain symlinks")
    parent = os.stat(os.path.dirname(path), follow_symlinks=False)
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise PermissionError("TURN secret parent must be private and administrator-owned")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > 128):
            raise PermissionError("TURN secret must be a private administrator-owned regular file")
        raw = stream.read(129).strip()
    if not re.fullmatch(rb"[A-Za-z0-9_-]{43,86}", raw):
        raise ValueError("TURN secret must contain at least 256 bits of generated material")
    return raw


def issue_credentials(secret: bytes, owner: str, *, ttl=120, host: str,
                      consent=False, trusted_caller=False, clock=time.time):
    if not trusted_caller or not consent:
        raise PermissionError("Trusted authenticated owner and scoped TURN consent required")
    if not isinstance(secret, bytes) or len(secret) < 43:
        raise ValueError("Strong private TURN secret required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", owner):
        raise ValueError("Invalid authenticated owner ID")
    if type(ttl) is not int or not 30 <= ttl <= 300:
        raise ValueError("TURN credentials must expire within 30–300 seconds")
    # An explicitly provisioned server hostname/IP, never a user supplied URL.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", host) or ".." in host:
        raise ValueError("TURN server must be a configured DNS name or IPv4 address")
    expires = int(clock())+ttl
    # Pseudonymize the owner to avoid storing raw user IDs in coturn usernames.
    scoped = hmac.new(secret, ("owner:"+owner).encode(), hashlib.sha256).hexdigest()[:24]
    username = f"{expires}:{scoped}.{secrets.token_hex(8)}"
    password = base64.b64encode(hmac.new(secret, username.encode(), hashlib.sha1).digest()).decode()
    return {"schema": "nexvary.turn.credentials.v1", "transport": "tls", "host": host,
            "port": 5349, "uri": f"turns:{host}:5349?transport=tcp", "username": username, "password": password,
            "expires_at": expires, "ttl_seconds": ttl,
            "relay_transport": "udp", "scope": "verified_pbx_peer_only"}


def write_credentials(output, value):
    output = Path(os.path.abspath(output))
    parent = output.parent.stat()
    if os.path.realpath(output.parent) != str(output.parent) or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise PermissionError("Credential output parent must be private and administrator-owned")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-file", required=True)
    parser.add_argument("--owner", required=True, help="Trusted authenticated owner, never copied from a client body")
    parser.add_argument("--host", required=True, help="Provisioned TURN host matching its TLS certificate")
    parser.add_argument("--ttl", type=int, default=120)
    parser.add_argument("--consent", action="store_true", help="Operator confirms scoped owner consent")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    data = issue_credentials(read_secret(args.secret_file), args.owner, ttl=args.ttl,
                             host=args.host, consent=args.consent, trusted_caller=True)
    write_credentials(args.output, data)
    print("Private short-lived TURN credentials issued; no server activated.")

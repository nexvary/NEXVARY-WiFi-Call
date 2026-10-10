"""Authorized external cellular SIP gateway with durable budget reservation.

Only a trusted administrator may provision manifests. This accepts an existing
voice gateway's SIP/media service; it does not emulate a USB modem audio driver.
"""
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from .calls import Calls, Policy, Route, State, VoiceEvidence


def private_parent(path):
    path = os.path.abspath(path)
    if os.path.realpath(path) != path:
        raise PermissionError("Private state path must not contain symlinks")
    info = os.lstat(os.path.dirname(path))
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise PermissionError("Private state parent must be owned by service administrator and mode 0700")
    return path


def unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate manifest key")
        result[key] = value
    return result


def read_manifest(path, now=None):
    now = time.time() if now is None else now
    path = private_parent(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_size > 16384):
            raise PermissionError("Manifest must be a private admin-owned regular file of at most 16 KiB")
        raw = stream.read(16385)
        if len(raw) > 16384:
            raise ValueError("Manifest exceeds size limit")
    manifest = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be an object")
    if manifest.get("schema") != "nexvary.cellular-sip-gateway.v1":
        raise ValueError("Unknown gateway manifest")
    if (manifest.get("trusted_admin_consent") is not True or manifest.get("carrier_use_authorized") is not True
            or manifest.get("gateway_side_limits_verified") is not True
            or manifest.get("sip_tls_verified") is not True or manifest.get("srtp_verified") is not True
            or manifest.get("synthetic") is not False):
        raise PermissionError("Trusted real evidence, authorization and hardware-side limits required")
    gateway = manifest.get("gateway_id", "")
    owner_extension = manifest.get("owner_extension", "")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", gateway):
        raise ValueError("Invalid gateway ID")
    if not re.fullmatch(r"[1-9][0-9]{3,5}", owner_extension):
        raise ValueError("Invalid owner extension")
    ev = manifest.get("evidence", {})
    required = ("online", "sim_present", "registered", "voice_commands", "audio_interface",
                "inbound_verified", "outbound_verified", "two_way_audio_verified")
    if any(ev.get(key) is not True for key in required):
        raise PermissionError("Independent voice/SIM/audio evidence required")
    evidence = VoiceEvidence(gateway, **{k: ev[k] for k in required},
                             verified_at=float(ev["verified_at"]),
                             firmware=ev.get("firmware", ""), modem_model=ev.get("modem_model", ""))
    if not evidence.available(now):
        raise PermissionError("Gateway evidence stale")
    policy = Policy(frozenset(), True, frozenset(manifest["destinations"]),
                    int(manifest["max_seconds"]), Decimal(str(manifest["daily_budget"])),
                    Decimal(str(manifest["rate_per_minute"])), 1)
    if not policy.destinations or policy.rate_per_minute <= 0 or policy.daily_budget <= 0:
        raise ValueError("Explicit nonzero budget/rate and exact destinations required")
    return manifest, evidence, policy


class BudgetLedger:
    """SQLite transactional worst-case reservations; no automatic restart release.

All completed calls remain charged their reserved maximum until an operator
reconciles trustworthy CDRs. This intentionally favors avoiding unexpected fees.
"""
    def __init__(self, path):
        self.path = private_parent(path)
        # File and parent must be private. Caller chooses a private state directory.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1 or info.st_uid != os.getuid()):
                raise PermissionError("Ledger must be a private regular file")
        finally:
            os.close(fd)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, owner TEXT NOT NULL, day INTEGER NOT NULL, amount TEXT NOT NULL, state TEXT NOT NULL)")

    def reserve(self, call, budget):
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute("BEGIN IMMEDIATE")
            # active reservations from previous days also block further allocation:
            # a service restart must not permit another potentially live paid call.
            rows = db.execute("SELECT amount FROM reservations WHERE owner=? AND (day=? OR state='reserved')", (call.owner, call.budget_day)).fetchall()
            if sum((Decimal(r[0]) for r in rows), Decimal("0"))+call.reservation > budget:
                raise PermissionError("Durable daily budget exceeded")
            if db.execute("SELECT 1 FROM reservations WHERE owner=? AND state='reserved'", (call.owner,)).fetchone():
                raise PermissionError("Prior call must be confirmed ended")
            db.execute("INSERT INTO reservations VALUES (?,?,?,?,?)", (call.id, call.owner, call.budget_day, str(call.reservation), "reserved"))

    def confirm_ended(self, call_id):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE reservations SET state='ended' WHERE id=?", (call_id,))


class CellularController:
    def __init__(self, calls: Calls, pbx, ledger: BudgetLedger, manifests: dict[str, Path]):
        self.calls, self.pbx, self.ledger = calls, pbx, ledger
        self.manifests = dict(manifests)
        self.pending_hangups = set()

    def originate(self, owner, destination, gateway):
        # Freshly re-read trusted evidence for every call. No client-uploaded manifest.
        path = self.manifests.get(gateway)
        if path is None:
            raise PermissionError("Unprovisioned cellular gateway")
        manifest, evidence, policy = read_manifest(path, self.calls.clock())
        if manifest["owner"] != owner:
            raise PermissionError("Gateway belongs to another user")
        self.calls.policies[owner] = policy
        self.calls.gateways[gateway] = evidence
        call = self.calls.start(owner, destination, Route.CELLULAR, gateway)
        try:
            self.ledger.reserve(call, policy.daily_budget)
            result = self.pbx.request("POST", "/channels", {
                "endpoint": "PJSIP/"+manifest["owner_extension"],
                "context": "cellular-authorized-"+gateway,
                "extension": destination, "priority": 1,
                "channelId": call.id, "timeout": 30,
            })
            return call
        except Exception:
            self.calls.transition(call.id, State.FAILED, "cellular_setup_failed")
            # A timeout might mean PBX accepted the call. Never automatically release
            # its durable reservation or declare its media path terminated.
            raise

    def confirm_hangup(self, owner, call_id):
        call = self.calls.calls[call_id]
        if call.owner != owner:
            raise PermissionError("Call belongs to another user")
        self.pbx.hangup(call_id)
        if call.state not in (State.ENDED, State.FAILED):
            self.calls.transition(call_id, State.ENDED)
        self.ledger.confirm_ended(call_id)

    def tick(self):
        """Trusted service must run periodically; PBX also enforces media duration."""
        for gateway, path in self.manifests.items():
            try:
                _, evidence, _ = read_manifest(path, self.calls.clock())
            except (OSError, ValueError, TypeError, KeyError, PermissionError):
                evidence = VoiceEvidence(gateway)
            self.calls.gateways[gateway] = evidence
        self.pending_hangups.update(self.calls.terminate_due())
        for call_id in list(self.pending_hangups):
            try:
                self.pbx.hangup(call_id)
            except RuntimeError:
                continue
            self.ledger.confirm_ended(call_id)
            self.pending_hangups.discard(call_id)


def candidate_config(manifest_path, output, now=None):
    """Generate separate opt-in include files; never merge/start them automatically."""
    manifest, evidence, policy = read_manifest(manifest_path, now)
    output = Path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    gateway = manifest["gateway_id"]
    endpoint = "cellular-"+gateway
    secret = secrets.token_urlsafe(32)
    incoming = manifest["owner_extension"]
    pjsip = f"""[{endpoint}]
type=endpoint
transport=secure-tls
context=cellular-inbound-{gateway}
auth=auth-{endpoint}
aors={endpoint}
disallow=all
allow=ulaw,alaw
direct_media=no
media_encryption=sdes
media_encryption_optimistic=no
force_rport=yes
rewrite_contact=yes
rtp_symmetric=yes
rtp_timeout=30
allow_transfer=no
[{endpoint}]
type=aor
max_contacts=1
remove_existing=no
qualify_frequency=15
[auth-{endpoint}]
type=auth
auth_type=userpass
username={endpoint}
password={secret}
"""
    # Outgoing context has no include path from any authenticated app context.
    # Only loopback authenticated ARI can originate into it after budget reservation.
    dialplan = f"[cellular-authorized-{gateway}]\n"
    for destination in sorted(policy.destinations):
        dialplan += f"""exten => {destination},1,Set(TIMEOUT(absolute)={policy.max_seconds+30})
 same => n,Dial(PJSIP/{destination}@{endpoint},30,L({policy.max_seconds*1000}))
 same => n,Hangup()
"""
    dialplan += f"""[cellular-inbound-{gateway}]
exten => {incoming},1,Set(TIMEOUT(absolute)={policy.max_seconds+30})
 same => n,Set(CALLERID(name)=Cellular gateway)
 same => n,Dial(PJSIP/{incoming},30,L({policy.max_seconds*1000}))
 same => n,Hangup()
"""
    import os
    for name, body in {"cellular-pjsip.conf": pjsip, "cellular-extensions.conf": dialplan,
                       "gateway-account.json": json.dumps({"username": endpoint, "password": secret, "tls": True, "srtp": "required", "incoming_target": incoming}, indent=2)}.items():
        fd = os.open(output/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(body)
    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    candidate_config(args.manifest, args.output)
    print("Candidate cellular include files generated privately; no service activated.")

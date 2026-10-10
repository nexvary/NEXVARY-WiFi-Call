# WiFi-Call USB AKA integration


The existing engine factory can now explicitly select a standalone USB mTLS
client instead of PhoneAkaBackend. Existing phone configurations remain valid.
The USB client is copied into the reviewed hardened engine stage, without GUI
or repo runtime dependencies. USB Studio offers a foreground opt-in bridge
session, at most 300 seconds, <=32 authentications, revoked on stop. It listens
only on 127.0.0.1; a separately provisioned private tunnel is required between
machines. Certificate CA validation, both peer pins, client certificates and
short-lived scoped token remain mandatory. No arbitrary APDU route exists.

Provisioned certificates/private keys are never generated from public CI
fixtures. Keep configuration and keys in owner-only storage (Linux mode0600;
Windows private owner ACL). Supply an actually discovered USIM AID and proven
AT port; never substitute the K3770 SELECT evidence as proof of authentication.
Run: `python -m nexvary_usim_lab bridge --config /private/session.json --consent`.
The portable EXE accepts the same `bridge --config ... --consent` arguments.

Bridge configuration keys: serial_port, device_key, aid, token, server_cert,
server_key, client_ca, client_pin, port. Token is a freshly provisioned random
32–128 character base64url value matching the engine configuration; port must
be an explicit 1–65535 loopback port. Do not put secrets in command-line args.

Engine private configuration keys: backend="usb", port, device_key, token,
server_ca, client_cert, client_key, server_pin; optional identity is an explicitly
owner/operator-provisioned carrier NAI. Neither project extracts IMSI/Ki/OPc or
invents an identity. `NEXVARY_ENGINE_AUTH_FILE` selects the owned mode0600 file.

Hardware/operator gates still required: real card access through the explicitly selected
transport (CCHO/CGLA only for logical mode), actual USIM AKA
SUCCESS or SYNC_FAILURE, authorized subscriber NAI, ePDG reachability, entitlement,
IKEv2/IPsec, IMS registration, incoming/outgoing calls and audio. No call server
or user's deployed WiFi-Call installation was changed. No claimed successful
call or live carrier authentication is contained in this release.

## Virtual SIM Reader / basic-channel CSIM — 0.10.0

Physical PC/SC readers are optional. On USB Studio host, explicitly choose
`"transport": "csim"` in the private bridge configuration to use the new
basic-channel implementation. Default remains the existing CCHO/CGLA backend;
there is **no automatic fallback or retransmission** after a failed challenge.
The CSIM backend discovers EF_DIR and matches the authorized AID on the current
card before issuing a single AUTHENTICATE. Transport is T=0, not an unvalidated
case-4 APDU with a trailing Le sent to a TPDU modem.

The existing `backend="usb"` engine configuration, mTLS client and caller
interface work with either local backend. Read-only Virtual PC/SC and the AKA
broker are independent: PC/SC does not accept AUTHENTICATE, arbitrary APDUs,
subscriber files, PIN or writes. Transport ATR/session-reset emulation is not
physical UICC equivalence. The new `virtual_sim_evidence.parse_reader_evidence`
imports bounded progress as untrusted context and cannot enable the gateway.

Run the USB host locally; a VPS cannot access an absent physical modem.
Keep the broker on loopback with provisioned mTLS plus a separately configured
private tunnel. Existing server preflight/isolation gates stay in force.
No Outline, firewall, host route, production container or deployed service
changes are performed by this integration.

Owner screenshot dated 2026-10-10 (USB Studio 0.10.1) now shows EF_DIR read
and USIM ADF selection on K3770 / 21.023.04.00.11. This is owner-supplied
physical-device evidence; JSON and independent retest are pending. Current
VID/PID and external PC/SC access are not established by that screenshot.
Still required: a real authorized operator challenge, AKA result, carrier
eligibility, ePDG, IMS and calls. This observation does not enable the gateway.
CCHO/CGLA are no longer mandatory for the explicitly selected CSIM backend.

## 0.10.1 boundary hardening

The independent USB client consumes each challenge once and latches its session unavailable after a dispatched request fails or returns malformed/unauthorized output. It cannot silently reconnect with a fresh request ID after an uncertain card outcome. The local CSIM backend revokes authorization after operation failure; the host bridge checks authorization again before serializing success. New owner consent/provisioned authorization is required to resume.

`server/engine/strongswan_card_adapter.py` implements a **staging callback contract**, reviewed against strongSwan `src/libsimaka/simaka_card.h` at a718759e5a2de5aba8c8da985c773a2ab9cff186. `get_quintuplet` maps the existing pinned mTLS USB backend to SUCCESS / FAILED / INVALID_STATE and CK/IK/RES in native API order. `resync` consumes cached AUTS for the matching identity/RAND once within 30 seconds, without a second AUTH. Identity must match the explicit provisioned NAI. No GSM triplet emulation, software Ki/OPc, public APDU endpoint, persistent quintuplet database, pseudonym or fast-reauthentication store is added.

Tests use synthetic callback data and an actual TLS roundtrip against USB Studio. This Python adapter is **not a native charon plugin**. Native libsimaka plugin wiring, process isolation and secret-memory review remain required before deployment. No strongSwan process, IPsec route, gateway, ePDG session, IMS registration or call was started by these tests. Upstream interface is GPL-2.0-or-later; no source from it was copied into this Python adapter. A future linked native plugin must comply with applicable strongSwan licenses.

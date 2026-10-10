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

Still required in the field: EF_DIR/ADF on the actual K3770 firmware, a real
operator challenge, AKA result, carrier eligibility, ePDG, IMS and calls.
CCHO/CGLA are no longer mandatory for the explicitly selected CSIM backend.

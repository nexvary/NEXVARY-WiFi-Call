# External SIM voice gateway integration

This adapter connects an independently proven cellular voice gateway through
authenticated SIP TLS with mandatory SRTP. A local gateway holds the real SIM
where cellular coverage exists. Asterisk stays on its isolated network; Android
uses its own authenticated account over Internet. This is not a USB audio driver,
SIM key extraction, generic modem firmware fix, or verified K3770 voice support.

The API is `server/multipath/cellular.py`. Its trusted controller can originate
an actual ARI call: it rings the user's internal account first, then the approved
PJSIP dialplan connects that answered user to the external voice trunk. Incoming
calls from the authenticated trunk ring only the configured internal account.
The hardware gateway must translate cellular ringing, answer, release and duplex
audio into SIP; each hardware gateway's firmware/audio interface needs field
verification. No chan_dongle module is implicitly used.

## Safe activation boundary

A trusted administrator provisions a private manifest with schema
`nexvary.cellular-sip-gateway.v1`. Required fields are:

| Field | Required evidence or configuration |
|---|---|
| `gateway_id` | Unique safe identifier, e.g. `local-voice-1` |
| `owner`, `owner_extension` | Authenticated owner and exact internal account |
| `trusted_admin_consent` | Boolean true after scoped owner consent |
| `carrier_use_authorized` | Boolean true after verifying permitted carrier use |
| `gateway_side_limits_verified` | Independent duration, destination and concurrency enforcement at hardware gateway |
| `sip_tls_verified`, `srtp_verified` | Successful certificate-validated signalling and encrypted audio verification |
| `synthetic` | False only for actual field observations |
| `destinations` | Nonempty list of exact E.164 destinations; no wildcard/premium/international default |
| `max_seconds`, `daily_budget`, `rate_per_minute` | Explicit positive limits and conservative known cost rate |
| `evidence` | Independent true `online`, `sim_present`, `registered`, `voice_commands`, `audio_interface`, `inbound_verified`, `outbound_verified`, `two_way_audio_verified`; observed `firmware`, `modem_model`, `verified_at` |

Fresh trusted evidence expires after five minutes. It must come from an
authenticated observer/operator; an Android request must never upload or choose
its own evidence manifest. A heartbeat cannot establish voice capability, AKA,
IMS or field verification. No sample manifest asserts a working modem.
The manifest and budget database must be regular non-symlink files owned by
the trusted service administrator, mode 0600, in a parent owned by that same
account with mode 0700. Manifest reads are bounded to 16 KiB and reject duplicate
JSON keys. The trusted service account is the administrative boundary, not an
untrusted app user or shared web-upload account.

After all prerequisites really pass, this command creates private *candidate*
configuration and credentials without activating or modifying a service:

```bash
PYTHONPATH=server python3 -m multipath.cellular \
  --manifest /private/trusted-gateway.json --output /private/new-cellular-candidate
```

An operator may review and explicitly include `cellular-pjsip.conf` in the
isolated PBX `pjsip.conf` and `cellular-extensions.conf` in `extensions.conf`.
Provision only the hardware gateway with `gateway-account.json`. The adapter
requires that gateway to REGISTER to the PBX over TLS, require server certificate
validation and SDES-SRTP, and send cellular inbound calls to the supplied
`incoming_target`. Never publish the credential JSON. This is a separate opt-in
step, not part of automatic setup or a host-server install.

The outgoing context has exact permitted destinations and **no include from
the Android/internal endpoint contexts**. Untrusted SIP clients cannot bypass
cost policy by directly dialing a cellular number. The only origination path is
the authenticated private ARI control service after admission. Keep ARI private;
do not expose these Python objects directly as unauthenticated web endpoints.
The new controller is a backend integration API; a public Android cellular-call
control endpoint has not been enabled by this patch.

## Accounting and disconnect behavior

`BudgetLedger` uses SQLite transactions to reserve the worst-case rounded-up
cost before opening a channel. Active reservations survive restart and continue
to block the owner until PBX call termination is confirmed. An ARI timeout may
mean the PBX accepted a call, so the controller never silently releases its
reservation. Completed calls retain the conservative reserved cost; reconciling
lower actual costs requires trustworthy CDRs and an administrative policy. The
ledger is not a carrier bill or a guaranteed tariff calculator.

Run `CellularController.tick()` periodically in the trusted service. It refreshes
evidence, marks lost SIM/network/voice gateway unavailable, terminates due calls
and retries failed teardown. Asterisk also enforces a maximum dial duration.
The gateway must have independent verified limits to prevent paid calls from
continuing after PBX or control-server failures. After a restart, reconcile
pending reservations with PBX and hardware CDRs before clearing them. Do not
release reservations merely because the app disconnected.

The unit tests use explicitly synthetic manifests and a mocked PBX, exercising
admission, isolation, injected identifiers, stale evidence, ownership, durable
budgets and uncertain timeouts. They are never modem or carrier evidence. The
separate live synthetic PBX harness tests only internal calls. Actual cellular
integration remains unverified until a compliant voice gateway, SIM/operator,
both call directions and two-way audio are field tested.

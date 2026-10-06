# Bounded initial ePDG exchange

This independent diagnostic uses Python's standard library. It does not execute upstream gateway code, authenticate the SIM, establish IPsec, register IMS, open listening ports, or change services, routes, DNS or firewall rules. It requires no sudo. Full gateway execution remains blocked.

## 1. Inspect the prepared upstream source

```bash
cd ~/nexvary-wifi-panel
git pull --ff-only origin dev/foundation
python3 server/engine/audit_gateway.py --source server/work/upstream
```

The audit is read-only. Exact revision, clean checkout and seven pinned source/license hashes must match. The JSON lists potential mutation sites and remaining blockers without printing command arguments or identities. A verified inventory intentionally returns exit code **2** because `executable` is false; code **1** means integrity was refused. The inventory is not a complete static security proof and never unlocks execution.

## 2. Confirm current DNS, then test one address

First print the plan (no network traffic):

```bash
python3 server/engine/epdg_probe.py
```

On the actual VPS, confirm current DNS for the carrier hostname:

```bash
timeout 10 getent ahosts epdg.epc.mnc002.mcc602.pub.3gppnetwork.org
```

The user previously observed `105.198.254.100` and `105.199.1.128`. Only use an address still returned by the current lookup. For example, if `105.198.254.100` is still present:

```bash
python3 server/engine/epdg_probe.py --probe \
  --host epdg.epc.mnc002.mcc602.pub.3gppnetwork.org \
  --address 105.198.254.100
```

The address is explicit so a blocking DNS resolver cannot extend the probe. This tool does not prove that the chosen IP belongs to the hostname; reviewing the DNS result is a separate step. It permits only public unicast numeric addresses and a canonical 3GPP ePDG hostname. It sends exactly one initial IKEv2 UDP/500 request with a fresh SPI, nonce and ephemeral group-14 key exchange. It waits for a bounded response, with no retries, COOKIE resend, IKE_AUTH or AKA request. Do not repeatedly loop it.

## Interpreting the result

A correlated response proves only that a syntactically valid IKE response was received for this request from the selected UDP endpoint. COOKIE, INVALID_KE_PAYLOAD and NO_PROPOSAL_CHOSEN are useful diagnostics; they are not SIM authentication failures. A matching proposal/key-exchange/nonce response is still unauthenticated. The responder's identity is not verified during IKE_SA_INIT. No result sets AKA, IPsec or IMS to verified, and this diagnostic does not change the panel's eight carrier stages.

No reply is inconclusive: it may reflect network filtering, geolocation policy, rate limiting, the selected proposal, endpoint availability or transport conditions. It does not prove the carrier or project cannot work. A malformed/unrelated response must not count as a correlated response.

The final live milestones still require a genuine authorized SIM authentication backend, real carrier/subscriber configuration, reviewed isolated gateway egress and independent IMS/calling/audio tests.

Primary protocol references: [RFC 7296](https://www.rfc-editor.org/rfc/rfc7296.html), [RFC 3526 group 14](https://www.rfc-editor.org/rfc/rfc3526.html).

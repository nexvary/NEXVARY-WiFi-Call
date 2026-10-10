# Authorized foreground Phone-as-SIM bridge

Android 0.5.0-alpha01 adds a transient AKA relay to the existing authenticated panel. Pairing, a received diagnostic report, and successful synthetic transport tests do not prove a real SIM computation, SWu authentication, IMS registration or a call.

## Update an existing owned panel

```bash
cd ~/nexvary-wifi-panel
git pull --ff-only origin dev/foundation
sudo bash server/update-panel.sh --update
sudo systemctl is-active nexvary-wifi-panel.service
```

The updater preserves the existing HTTPS public origin, password and paired-phone database. It restarts only the owned NEXVARY service and archives the prior code/unit. It does not alter nginx, Outline, FG MTM, firewall rules or routes. No gateway is installed by this update.

In Android select the actual SIM, run the capability check, then open More → Gateway. Existing QR/manual pairing and explicit diagnostic reporting remain available. The AKA section requires explicit consent, carrier privileges, a selected active subscription and phone permission. A session lasts at most five minutes while the screen remains in the foreground. Leaving the screen, changing the selected SIM, revoking pairing or pressing Stop ends the session. Authentication cannot continue in the background.

When `hasCarrierPrivileges()` is false, the application cannot use `getIccAuthentication()` for that subscription. A server connection cannot grant this Android/UICC permission. The app must retain this blocked state instead of inventing authentication results or bypassing the platform.

## Separate engine authorization

Engine requests use the fixed loopback endpoint `127.0.0.1:8787/api/engine/aka`, a separately provisioned private credential and a canonical paired-device UUID. Requests carrying browser/proxy forwarding headers are refused. Engine access is disabled by default; neither the admin password nor phone token enables it. See [engine provisioning and audited staging](../engine/README.md).

Only one challenge may be outstanding for a phone. Each challenge expires within 30 seconds, and expired, duplicate, mismatched, stopped or revoked responses are rejected. Sessions and challenge material remain in bounded memory. The database and panel inventory contain no RAND/AUTN, RES, CK, IK or AUTS. Error responses contain safe state codes only. No Ki, OP/OPc, SIM PIN, hidden API, root access or RIL modification is used.

The loopback adapter validates canonical Android DB/DC responses and fails closed on unavailable phones, unauthorized SIMs, malformed results or network errors. These unit/HTTP tests use synthetic fixtures. A real carrier challenge, an authorized SIM response and independent protocol evidence are required before any gateway stage can be verified.

## Remaining gateway gates

Pinned upstream preparation and hardening create an audit copy only. Generated gateway entry points are intentionally blocked pending review of privileged system/network mutations and dependency licenses. Real carrier identity/NAI configuration is also required; sanitized diagnostic reports cannot supply an IMSI. Do not run upstream Docker/install commands on the shared VPS as a substitute for these reviews.

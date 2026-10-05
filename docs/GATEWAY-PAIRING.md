# Phone/panel pairing — 0.4.0-alpha01

This version adds a real control-plane contract between the Android app and the panel. It does not install a SWu/IPsec/IMS engine, perform AKA, or verify carrier calls. Every gateway stage retains independent untested evidence after a phone report.

## Workflow

1. Install the panel on Ubuntu 24.04. For phone access, set `--public-origin https://YOUR-DNS-NAME` and configure a reviewed HTTPS reverse proxy with a valid Android-trusted certificate. The server stays on 127.0.0.1:8787; never expose the raw HTTP port. The supplied Caddy example fixes the backend Host header and preserves the browser Origin.
2. Log in to the panel over HTTPS and generate a pairing code. It expires after ten minutes and works once.
3. In Android: More → Server connection. Enter the same HTTPS origin and the code. Pairing validates the server's standard TLS certificate; it does not accept self-signed certificates, insecure HTTP or redirects.
4. Press Send diagnostic report. No background upload occurs. The panel displays received time, coarse network, selected slot, SIM count, Android/API version and Phone-as-SIM capability. This is self-reported device capability, not verified carrier authentication.
5. Revoke a phone from the panel or disconnect from Android. A revoked bearer cannot submit reports. Android can clear an already-invalid credential by pressing disconnect.

## Privacy and persistence

The JSON schema contains exactly `schema_version`, `sim_count`, `selected_slot`, `network`, `phone_as_sim`, `app_version`, and `android_api`. No phone number, IMSI, ICCID, MCC/MNC, carrier identifier, IP address, Ki, OPc, AKA result or session key is accepted. Unknown fields are rejected rather than retained. The server timestamps receipt itself. Slot indices are zero-based; null means no known selection.

Codes and bearer tokens are stored only as SHA-256 hashes in a private bounded SQLite database. The plaintext bearer is returned once to the phone over TLS. Android encrypts the pairing using AES-GCM and AndroidKeyStore; the preferences are explicitly excluded from cloud backup and device transfer. The panel never lists the bearer. Authentication payloads are not logged.

A recent-report label means a report was received within 120 seconds; it is not a heartbeat, persistent tunnel or VoWiFi readiness claim. There is no gateway-driven AKA request endpoint in this version.

## Before actual deployment

Run read-only preflight on the intended host. Review existing reverse proxies, DNS and ports before adding a site; do not replace other sites' configuration. A public origin alone does not install DNS/TLS. An existing owned panel can be updated with `server/update-panel.sh`; updates preserve password and phone state, archive prior code, and roll back code on failed startup. Read `server/docs/ADMIN-PANEL.md` for actual install/update commands.

## Verification

Server tests cover one-use/expired codes, concurrent consumption, revocation, allowlist rejection, persistence, origin/host protection and truthful carrier states. Browser checks perform a full pairing/report/revoke flow using a CI fixture. Android instrumentation covers the real JSON/client response contract with a replaced test transport, encrypted credential persistence/tampering and seven-locale screen navigation. TLS on the intended domain and the physical phone/SIM remain deployment checks, distinct from these CI tests.

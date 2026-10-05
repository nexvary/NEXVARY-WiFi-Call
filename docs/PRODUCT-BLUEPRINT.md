# Product Blueprint — Prevention-First

## Development doctrine
Research and plan before implementation. Anticipate failure modes before they become architecture debt. Build a small modular nucleus that can be replaced or extended without rewriting the product. Every capability must have an evidence gate; unsupported carrier behavior is never presented as working.

## Product definition
NEXVARY WiFi Call is a carrier-aware calling platform. Its primary job is to determine the best authorized Wi-Fi calling path available to the user and provide a clear call experience and diagnostics. It is not defined as a generic SIP dialer.

## User surfaces
1. Home: readiness state and best available path.
2. Call: dial/receive UI when the selected path permits app-controlled calling.
3. SIM & Carrier: per-subscription capability/evidence.
4. Wi-Fi Health: validation, captive portal, VPN, DNS, latency variability and loss where measurable.
5. Compatibility: country/operator/device evidence matrix.
6. Diagnostics: actionable causes, not raw engineering codes.
7. Privacy & Security: local secrets policy, redacted export, consent.
8. Settings/About: language, accessibility, gateway/SIP configuration where applicable.

## Replaceable architecture
- app-ui: presentation/navigation only.
- core-domain: path selection, readiness, evidence and errors.
- android-platform: Connectivity/Telephony public-API adapters.
- carrier-catalog: signed/versioned operator evidence, never credentials.
- diagnostics: independent probes and redaction.
- native-wfc-adapter: platform-supported capability inspection only.
- gateway-client: authenticated protocol boundary for authorized external VoWiFi runtime.
- sip-adapter: optional explicit-credential fallback.
- media: later call media abstraction.
- test-fixtures: synthetic/redacted fixtures only.

No UI screen talks directly to Telephony, IMS, SIP or gateway implementations. Interfaces isolate every path.

## Prevention gates before feature coding
- Verify Android API/permission feasibility.
- Verify carrier privilege requirements.
- Verify dual-SIM behavior.
- Define degraded behavior when permissions/API are unavailable.
- Define offline/captive portal/VPN/IPv6 behavior.
- Define evidence required before calling a carrier supported.
- Define privacy/redaction before logs exist.
- Pin CI toolchain versions and dependency compatibility.
- Keep workflow syntax minimal and add manual dispatch.
- Require unit tests before integration tests.
- Never extract or persist long-term SIM authentication secrets.
- Do not claim emergency calling until independently validated.

## Expansion targets
4G/EPC IMS over untrusted Wi-Fi; 5G Core Wi-Fi Calling; VoLTE/VoNR interworking research; carrier lab profiles; enterprise/private IMS; authorized gateway appliances; quality analytics; optional SMS where verified; multi-language UI; accessibility; signed updates.

## Definition of done
A feature is done only when code, tests and evidence agree. A carrier reaches production-candidate only after reproducible real-device interoperability. Final release gate requires verified inbound and outbound Wi-Fi voice with two-way audio, recovery tests and documented limitations.

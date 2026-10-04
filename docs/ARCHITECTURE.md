# Architecture

## Product paths

NEXVARY WiFi Call deliberately supports multiple execution paths behind one capability model.

1. **Native carrier path** — use platform/carrier-supported Wi-Fi Calling when Android and the carrier expose an authorized path.
2. **External VoWiFi gateway path** — standards-oriented SWu/ePDG + IMS runtime on supported Linux/modem/SIM hardware.
3. **SIP fallback path** — optional interoperable VoIP for deployments that explicitly provide SIP credentials. It is never presented as carrier VoWiFi.

## Core boundaries

- `app-android`: UI, diagnostics, permissions, call UX.
- `core-model`: capability/result/state models; no Android dependency.
- `carrier-compat`: MCC/MNC profiles, entitlement requirements, evidence status.
- `native-adapter`: Android-supported carrier/IMS capability inspection. No hidden-API dependency in production.
- `gateway-protocol`: authenticated client protocol to an external NEXVARY gateway.
- `gateway`: future Linux runtime integration boundary for SIM/AKA, SWu/ePDG, IMS, SIP/RTP.
- `test-fixtures`: redacted protocol fixtures only.

## VoWiFi flow

SIM/USIM -> AKA/AKA' -> IKEv2 SWu -> ePDG -> IPsec/ESP -> P-CSCF -> IMS REGISTER -> SIP/MMTel -> RTP/SRTP.

The implementation must keep SIM secrets on the secure SIM/modem boundary. Logs must redact IMSI, IMPI/IMPU, RAND/AUTN/RES/AUTS, IPsec keys, SIP authorization material and phone numbers.

## Evidence gates

A carrier is never marked supported merely because its ePDG DNS name resolves.

Levels:
- UNKNOWN
- DISCOVERED
- EPDG_REACHABLE
- SWU_AUTHENTICATED
- IMS_REGISTERED
- OUTBOUND_VOICE_VERIFIED
- INBOUND_VOICE_VERIFIED
- SMS_VERIFIED
- PRODUCTION_CANDIDATE

Emergency calling remains disabled in experimental gateway mode until carrier/regulatory validation is complete.

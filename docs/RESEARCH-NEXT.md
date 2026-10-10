# Research-derived Expansion

## Android opportunities
- NetworkCallback can maintain live readiness without polling.
- LinkProperties exposes DNS servers, routes, local addresses and proxy context useful for explainable diagnostics.
- DnsResolver on Android 10+ can support asynchronous record types beyond A/AAAA; ePDG discovery should be an isolated resolver component with API-level fallback.
- Jetpack Core-Telecom provides a stable CallsManager surface for app-controlled VoIP integration. Evaluate it for gateway/SIP calls, Bluetooth/wearable/automotive visibility and audio routing; do not conflate this with native carrier IMS control.
- Unified call-history integration is optional and consent-sensitive.

## 5G expansion
GSMA TS.63 covers Wi-Fi Calling requirements for 5G SA and scenarios spanning 5GC and EPC. Keep access discovery abstract: ePDG is not the only future non-3GPP access model. Research N3IWF/TNGF as separate adapters rather than mutating the EPC adapter.

## Candidate differentiators
- Live readiness timeline.
- Per-SIM compatibility and best-path comparison.
- DNS/ePDG discovery inspector with evidence semantics.
- Before-call network quality baseline and after-call quality comparison for app-controlled calls.
- “What changed?” explanation after Wi-Fi/VPN/DNS transitions.
- Optional system call-history integration for app-controlled calls.
- Bluetooth/headset/wearable/automotive call integration through Android Telecom where applicable.
- Carrier evidence freshness and regression detection.
- Local exportable support report with irreversible redaction.
- Lab mode separated from consumer mode.

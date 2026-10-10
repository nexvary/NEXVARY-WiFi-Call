# Evidence-driven Feature Backlog

## Build next
- Readiness timeline: show why readiness changed after Wi-Fi handover, VPN or captive portal.
- Dual-SIM comparison: evaluate each active subscription independently.
- Network quality score: latency, variability and measurable loss; never call generic variability RTP jitter.
- Pre-call health check: Wi-Fi validation, captive portal, VPN, DNS context, carrier evidence and selected path.
- Redacted diagnostic bundle with explicit user consent.
- Compatibility card with evidence date and level, not a binary marketing badge.
- Actionable repair assistant: every blocker maps to safe user actions.
- Offline history: recent quality/readiness kept locally with bounded retention.

## Research before implementation
- Private DNS impact and DNS resolver visibility across supported Android versions.
- Wi-Fi signal metrics and permission behavior by Android API level.
- Seamless handover expectations between Wi-Fi and cellular for native carrier calls versus app-controlled paths.
- Android Telecom integration for app-controlled calls.
- Audio focus, Bluetooth/headset routing and accessibility.
- IPv6-only and NAT64 test lab.
- 5G SA Wi-Fi Calling architecture and N3IWF/TNGF evolution without coupling the current EPC model.
- Optional operator-supplied entitlement/onboarding integration where documented and authorized.

## Product differentiators
- Explainability: “why calling is unavailable” rather than a generic error.
- Evidence freshness: compatibility expires and is revalidated.
- Network-change replay: correlate quality/readiness changes with transport changes.
- Privacy-first diagnostics: identifiers redacted before storage/export.
- Modular call-path engine: native carrier, authorized gateway, explicit SIP, future authorized transports.

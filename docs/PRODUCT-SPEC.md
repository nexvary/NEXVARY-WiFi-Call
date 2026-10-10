# Product Specification

## Core promise
Tell the user whether high-quality calling over the current Wi-Fi is actually available, why it is or is not available, and select only an authorized verified call path.

## Primary states
- READY_NATIVE: carrier/platform Wi-Fi Calling is verified available.
- READY_GATEWAY: authorized external gateway path is configured and healthy.
- READY_SIP: explicit SIP fallback is configured.
- DEGRADED: Wi-Fi exists but a blocking or quality condition exists.
- RESTRICTED: Android/carrier privilege prevents a reliable determination.
- UNSUPPORTED: evidence says this carrier/device/path is not supported.
- UNKNOWN: insufficient evidence; never display as supported.

## First-run flow
Language -> privacy summary -> network readiness -> subscription selection -> carrier evidence lookup -> path evaluation -> Home.

## Home
One dominant readiness card, selected SIM, current Wi-Fi state, selected path, quality summary, and one primary action. Technical detail stays behind Diagnostics.

## Diagnostics
Checks are layered: device -> subscription -> Wi-Fi -> internet validation -> captive portal/VPN -> DNS -> carrier evidence -> path-specific checks. Every failed check has a user-facing remediation and a machine-readable reason.

## Calls
The app exposes a dial/receive surface only for paths the app is authorized to control. Native carrier calls remain system-owned unless Android/carrier integration explicitly permits otherwise.

## Compatibility
Support is evidence-based per country + MCC/MNC + device/API context. Discovery is not proof of calling. Evidence expires and can be downgraded.

## Privacy
No Ki extraction. No long-term SIM secret storage. Diagnostic exports are redacted by construction. Phone identifiers are optional and minimized.

## Extensibility
Path engines, probes, carrier catalog, media and UI are independent ports. A new transport or future 5G path must be addable without changing screen/domain contracts.

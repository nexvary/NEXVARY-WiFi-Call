# Build Risk Register

| Risk | Prevention | Verification |
|---|---|---|
| Workflow never starts | Keep CI workflow valid on default-branch integration path; include push, PR and manual dispatch | A recorded Actions run exists |
| Gradle/plugin incompatibility | Pin JDK, Gradle and Android/Kotlin plugins as a tested set | Clean CI build |
| Compose/compiler mismatch | Use compatible Kotlin/Compose toolchain and upgrade as one unit | assembleDebug + tests |
| Missing wrapper | Either commit verified Gradle wrapper or explicitly provision pinned Gradle in CI | Clean checkout build |
| Permission-dependent crashes | Capability checks and graceful unknown/restricted states | permission-denied tests |
| Carrier API inaccessible | Public API adapter; never assume carrier privileges | non-carrier app device test |
| Dual-SIM ambiguity | Subscription-scoped model from first implementation | two active subscriptions test |
| False VoWiFi support claim | Evidence ladder; UI distinguishes discovered/reachable/registered/call-verified | carrier lab evidence |
| Captive portal/VPN interference | Detect before carrier probes | controlled network tests |
| IPv6-only/CGNAT differences | IP-family-neutral diagnostics | IPv4/IPv6 test matrix |
| Sensitive diagnostic leakage | Redaction before persistence/export | redaction unit tests |
| Architecture lock-in | Ports/adapters between UI, platform, gateway, SIP and media | fake adapters in tests |
| Background/battery failures | Explicit foreground/background lifecycle design | Android restriction matrix |
| Call audio regressions | Media abstraction + route/focus tests | physical-device call tests |
| Emergency-call ambiguity | Experimental modes do not advertise emergency support | release checklist |

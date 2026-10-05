# Phone-as-SIM PoC

## Goal
Prove whether an Android handset can act as the USIM AKA endpoint for the NEXVARY VoWiFi Gateway without extracting Ki and without buying an external SIM reader.

## Architecture
Gateway -> authenticated challenge transport -> Android AKA adapter -> TelephonyManager/UICC -> USIM -> AKA response -> Gateway.

The long-term SIM key must never leave the UICC. Only protocol challenge/response material required for an authorized AKA exchange may cross the adapter boundary.

## Android feasibility gate
Android exposes UICC authentication through TelephonyManager.getIccAuthentication with APPTYPE_USIM and AUTHTYPE_EAP_AKA. Access is privileged: the runtime must have carrier privileges or an applicable ICC-auth permission granted by the platform. A normal downloadable app must therefore probe capability and fail closed rather than assuming access.

A third-party downloadable ImsService is not the product path. Android's full MMTEL ImsService integration is reserved for trusted preinstalled/system or carrier-selected packages. NEXVARY will keep IMS termination/gateway logic outside the ordinary APK unless an authorized OEM/carrier deployment exists.

## Decision tree
1. Detect telephony subscription and selected SIM.
2. Check carrier privileges for that subscription.
3. Check whether the platform exposes an authorized ICC-auth path to this package.
4. If authorized, run a non-secret capability probe; do not generate arbitrary live carrier authentication traffic.
5. If unavailable, mark PHONE_AS_SIM_RESTRICTED and use native carrier Wi-Fi Calling diagnostics or an external authorized SIM endpoint.
6. Never request root, extract Ki, patch the radio, or bypass carrier controls in the consumer build.

## Success criteria
- No Ki extraction/storage.
- Explicit authorized capability detected.
- USIM performs EAP-AKA computation internally.
- Gateway adapter receives only the minimum response material.
- Redacted logs.
- Per-subscription isolation.
- Replay-resistant authenticated transport.
- Physical carrier test only with a SIM/account authorized for the test.

## Current conclusion
This route can eliminate an external reader on devices/carriers that grant ICC authentication access. It cannot be assumed for arbitrary Play-distributed apps, so capability probing is mandatory before hardware purchase.

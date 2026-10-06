# Authorized Phone-as-SIM options

Checked 2026-10-06 against Android documentation and the Android 15 platform manifest. The actual paired phone's report says carrier privileges are unavailable for this application. This is a capability observation, not a failed live AKA result. Neither server connectivity, QR enrollment, device ownership nor normal `READ_PHONE_STATE` permission grants carrier privileges.

## Supported path

The current consumer build uses `TelephonyManager.createForSubscriptionId` and public `getIccAuthentication(APPTYPE_USIM, AUTHTYPE_EAP_AKA, ...)`, after verifying carrier privileges for the chosen subscription and the user's explicit foreground session. The SIM performs authentication internally. No Ki is read. Actual RAND/AUTN must come from a genuine authorized exchange; a sample challenge is not carrier evidence.

Carrier privilege rules on the UICC match the signing certificate and optionally the application package. The carrier controls these rules and can update them through an authorized OTA update. A carrier-approved application identity with corresponding UICC access rules is therefore a possible route; it requires carrier cooperation. A trial APK's signing certificate must not be confused with a stable production signing identity. Do not create, change or replace UICC rules yourself to obtain access.

## Alternatives and limits

| Option | Required authorization | Current assessment |
|---|---|---|
| Carrier-approved NEXVARY app | Carrier grants access for the app signing identity on this SIM | Not granted on the tested SIM; cooperation required |
| OEM/system integration | Manufacturer supplies an authorized system integration and permissions | Separate product/integration; not obtained by an ordinary APK install |
| Existing carrier app integration | Carrier exposes a documented, authenticated API that permits this specific use | No such interface verified for the tested carrier; another app's permission is not inherited |
| External USIM reader backend | Compatible reader/card, authorized on-card authentication and transient result transport | Possible engineering fallback, compatibility and live authentication still need verification |
| Modem with documented USIM authentication | Device vendor's documented support and authorized SIM access | Device-specific; no compatible device verified |

Android 15 declares `USE_ICC_AUTH_WITH_DEVICE_IDENTIFIER` as `signature|appop`. It is not an ordinary runtime permission that this consumer build can request with a permission dialog. Current online Android API documentation also describes newer permission changes; those must not be assumed to apply to Android 15. NEXVARY does not enable root, hidden APIs, RIL patches, identity/signature impersonation, software Ki authentication or permission bypasses as a workaround.

Bluetooth, USB tethering and Wi-Fi pairing do not by themselves expose an authorized UICC authentication API. Installing a third-party VoWiFi, entitlement or IMS implementation supplies protocol code, not access to a protected SIM. eSIM profile access rules still require the profile issuer's authorization; changing from a physical SIM to eSIM is not a verified workaround.

## What can advance before AKA

The server can independently verify source integrity, private transport and namespace isolation. A bounded initial IKE exchange can test whether an endpoint sends a correlated response without requesting SIM authentication. These checks do not establish carrier identity, authenticated IPsec, IMS registration, calls or audio. The full gateway execution gate remains active.

## Primary references

- [Android UICC carrier privileges and certificate rules](https://source.android.com/docs/core/connect/uicc)
- [Public TelephonyManager authentication API](https://developer.android.com/reference/android/telephony/TelephonyManager#getIccAuthentication(int,%20int,%20java.lang.String))
- [Android 15 platform permission declarations](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android15-release/core/res/AndroidManifest.xml)

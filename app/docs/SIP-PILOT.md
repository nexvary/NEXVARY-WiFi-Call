# Android internal SIP pilot — 0.7.0-alpha01

The existing application now has a Connection Center, internal extension keypad,
incoming answer/reject, outgoing call, microphone mute, speaker/earpiece selection,
user-selected single contact and session-only call history. Existing SIM/ePDG,
QR pairing, native carrier capability and consent workflows remain intact.

## What is implemented

- Actual `org.linphone:linphone-sdk-android:5.4.100` engine, not a simulated dialler.
- TLS-only SIP transport; SIP UDP/TCP listeners disabled; server certificate and
  hostname verification enabled. A trusted certificate matching the entered PBX
  hostname is required. No insecure certificate bypass exists.
- Mandatory SRTP on outgoing and answered calls. Audio-only, one active call.
- Optional STUN + ICE; no unapproved public STUN service is contacted by default.
- Runtime microphone permission, separate microphone foreground service and
  audio focus via the SDK. No hidden Android API or carrier privilege bypass.
- Password is not saved in preferences, Compose saved state or a configuration
  file. An in-memory SDK configuration is used; SDK SIP traces are disabled.
- Internal digits-only extensions, no arbitrary SIP URI or international prefix.
  Common emergency short codes are rejected. The PBX must separately enforce
  an explicit extension allowlist, account authentication and call limits.
- REGISTER does not promote a path to Available. SRTP negotiation is displayed
  distinctly from verified audible two-way audio and incoming/outgoing proof.
- Contact picker only reads the single user-selected phone data URI; it does not
  request bulk contacts access. Only a stored internal PBX extension can be dialled.

## Validation and honest limits

Resource parity validated for seven existing languages. New UI text is
translated into AR/EN/TR/ES/DE/IT/FR; native editorial review remains recommended. Instrumentation
captures Connection Center/dialler at 130% font scale in all seven locales and
checks unconfigured calls are disabled and cellular selection cannot initiate SIP.

The preceding 0.6.0 pilot passed actual production Android SDK integration
against a disposable Asterisk 20 instance in GitHub Actions: verified TLS
registration, incoming/outgoing calls, SRTP negotiation, positive audio upload/
download statistics, independently decrypted media and both BYEs. These were
synthetic emulator calls, not physical acoustic or cellular tests.

0.7.0 adds in-call DTMF through the public Call.sendDtmf API, optional TURN over
TLS with expiring in-memory credentials, private immutable notification Mute/End
actions, and explicit registration retry. CI must independently verify completed
RFC4733 events, notification actions, real disposable-PBX outage/recovery and
coturn TLS allocation/relay before claiming those operational outcomes.

TURN is opt-in: provision a matching trusted TLS certificate and a short-lived
credential from the trusted operator CLI. No shared TURN secret is sent to Android,
no password is persisted, and expired credentials block registration, dial and
answer. The issuer is not an unauthenticated public web endpoint. Successful
coturn relay tests alone do not prove Android chose a relay candidate or that
real-world CGNAT traversal succeeds.

Keep the app visible for incoming calls in this pilot. Push wake-up, killed-app
incoming calls, lock-screen/Telecom integration and physical Android background
reliability remain unverified. Notification actions apply to an existing call;
they do not start a microphone service from a background incoming push. Cellular
calls remain unavailable until voice-modem and operator integration proof exists.
No modem or SIM was used by these Android tests.

SDK source/API inspected from the exact 5.4.100 sources artifact and official
Android guide. UI screenshots are produced only by actual Android instrumentation,
not generated images.

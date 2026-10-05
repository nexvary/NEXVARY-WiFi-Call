# Android UI verification

## Scope of 0.3.0-alpha01

Development continues from `dev/foundation`. The domain engines and authorized
Android probes remain the source of facts; a UI color does not create evidence.

- NEXVARY dark dashboard, status ring, icon navigation and safe system-bar insets.
- Active SIM cards with persisted selection and separate permission/no-SIM states.
- Diagnostics pipeline, including non-invasive Phone-as-SIM privilege preflight.
- Consumer explanations and optional Lab evidence details.
- Seven selectable languages and Arabic RTL; Android 13+ per-app locale settings.
- Developer attribution and actionable website/email/Facebook links.

## Automated checks

Run `python3 scripts/validate_resources.py` for locale coverage, references,
Android escaping and matching format arguments. CI provisions JDK 17 and Gradle
8.9, then runs:

```
gradle :core-model:test :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest
```

The UI jobs use Android API 35 on Pixel 2 and Nexus 5 profiles. They exercise:

- Navigation, refresh, permission actions and in-app Back in all seven languages.
- A font scale of 1.3 and scroll access to lower cards and controls.
- Two actual subscription IDs in the SIM selector callback.
- Language changes and persistence through real activity recreation, including
  framework locale selection and Arabic layout direction.
- Installed launcher entry resolution, adaptive icon loading and launcher start.
- Actual landscape/portrait activity recreation and primary-action access.
- Website, email and both Facebook intents, intercepted before leaving the test
  app and compared against the required exact destination URLs.

`bash scripts/run_ui_checks.sh` runs instrumentation and preserves screenshot
PNGs outside app-owned storage before AGP cleans up. CI uploads screenshots,
instrumentation results, unit-test reports and lint reports. APK upload fails if
the expected APK does not exist. Installed icon output is rendered from the
launcher entry's actual APK resource, rather than a source asset preview.

## Visual review

Download each profile's UI-verification artifact and inspect Home, SIMs,
Diagnostics, More and About in the seven locales, plus actual-activity Arabic
and English Home, landscape/portrait and installed launcher icon images.
Review text clipping, spacing, contrast, navigation/system bars and RTL values.
Automated click tests and image production alone do not certify visual quality;
record the reviewed CI run and any remaining physical-device limitations in the
delivery report.

## Product boundary

This is an alpha diagnostics interface. Unmeasured quality and untested carrier
steps remain unverified. Carrier privilege availability is a preflight result,
not successful SIM AKA computation or a carrier session. No authentication
challenge is issued by this capability check. A readiness check does not prove
native VoWiFi, IMS registration, calls or audio. Physical dual-SIM hardware,
real AKA, gateway carrier sessions and bidirectional voice tests remain separate
integration checks described in `PHONE-AS-SIM-POC.md`.

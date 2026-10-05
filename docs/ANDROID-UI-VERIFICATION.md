# Android UI verification

## Scope of 0.2.0-alpha02

Development continues from dev/foundation, including the existing Phone-as-SIM
capability probe. No carrier transport or existing core engine was removed.

- Compose dark theme with a silver outline and turquoise actions.
- Four labeled navigation destinations with icons and working in-app Back.
- Scrollable content inside Scaffold system-bar insets.
- Fully localized screens, status values, blocker explanations and developer links.
- Arabic RTL and seven selectable languages, persisted across restart.
- Refresh runs the actual Android network/subscription probes; permission results
  and returning to the foreground refresh the dashboard.
- Active SIM selection resolves the previous dual-SIM ambiguity.
- No active SIM and missing permission are separate states.
- Developer links keep the existing attribution and handle unavailable apps.

## Checks

Run `python3 scripts/validate_resources.py` for complete locale coverage,
resource references, Android escaping and format arguments.

CI provisions JDK 17 and Gradle 8.9, then runs:

```
gradle :core-model:test :app:assembleDebug :app:assembleDebugAndroidTest
```

The UI job uses an API 35 Pixel 2 emulator. Parameterized tests exercise all
seven languages at font scale 1.3, permission callbacks, refresh, navigation,
scrolling and Back. It publishes screenshots and Android test reports.

## Product boundary

This is an alpha diagnostics interface. Network quality stays unmeasured until
real measurements exist. Unknown carrier evidence stays unknown. A readiness
check does not enable a carrier service or prove an actual call. Phone-as-SIM
remains the preflight described in PHONE-AS-SIM-POC.md; full gateway voice,
native carrier verification and physical dual-SIM tests remain separate work.

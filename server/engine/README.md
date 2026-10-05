# Audited staging boundary for Phone-as-SIM AKA

This directory contains a fail-closed transient AKA adapter and a **staging-only** hardening transformation for the pinned upstream gateway. It installs no packages, starts no process, changes no firewall/routes and performs no carrier authentication. The generated upstream entry points are deliberately blocked until remaining system/network mutation paths and dependencies have been reviewed. Passing these isolated tests proves no ePDG, IPsec, IMS registration, calling or audio success.

## Broker contract

The adapter uses a direct HTTP connection to `127.0.0.1:8787` with a 35-second maximum timeout. It does not use environment proxies, remote URL configuration, redirects, GET query parameters or automatic retries.

`POST /api/engine/aka`, `Authorization: Bearer <explicit engine credential>`:

```json
{"device_id":"selected-paired-device-uuid","rand":"32 hexadecimal characters","autn":"32 hexadecimal characters"}
```

The broker must independently require a selected, authorized, unrevoked phone and its explicit foreground authentication session. Pairing alone is insufficient. Phone carrier privileges/public authorized APIs remain mandatory; the bridge provides no privilege bypass. The engine credential is disabled unless separately provisioned. Never reuse the browser password or phone bearer as an engine credential.

Response fields are exactly `state` and `payload`. For `SUCCESS`, payload is canonical Base64 of the Android `0xDB` result: one-byte RES length 4–16, RES, CK length 16, CK, IK length 16, IK. For `SYNC_FAILURE`, it is canonical Base64 of `0xDC`, length 14, AUTS. Extra fields, invalid sizes, malformed binary/Base64, failed authentication, expired/revoked sessions, timeout, non-200 HTTP responses and unavailable brokers fail closed. There is no default RES/CK/IK or synthetic success.

The SWu first-attach API expects successful uppercase hexadecimal `(RES, CK, IK)` or synchronization failure `(AUTS, None, None)`. The upstream reauthentication path refuses synchronization failure; this work does not claim new protocol support. The AMI API expects `(RES, CK, IK, None)` or `(None, None, None, AUTS)`.

## Private engine authorization

Set `NEXVARY_ENGINE_AUTH_FILE` to a regular, non-symlink file owned by the executing UID with mode `0600`, containing exactly `token` and `device_id`. The file contains only the explicitly scoped engine authorization and selected paired device ID. No Ki, OP/OPc, SIM identity or AKA response belongs in it. No default credential is installed or enabled by this work.

The adapter does not print/log requests, responses or exceptions and retains authentication outputs only in process memory. Python cannot guarantee zeroization of immutable objects; preventing secret persistence/logging and limiting lifetime are necessary constraints, not a claim of secure memory erasure. Do not enable packet capture, core dumps, protocol debugging or upstream decryption-table exports around transient key material.

## Real identity gate

Sanitized phone reports deliberately contain no IMSI. `identity()` therefore raises an unavailable error. A real, independently authorized operator identity/carrier configuration is required before the upstream protocol can construct its NAI. No fake/default IMSI, MCC/MNC or guessed operator identity is acceptable. This bridge currently supplies neither identity acquisition nor a complete gateway configuration.

## License and dependency gate

Upstream source is pinned to `pagecat/vowifi_gateway` revision `e3719840b93961f933aab3dac8bd2641936e2bcc`. Its root `LICENSE` is MIT, copyright 2026 pagecat; the staging tool preserves that notice and records modifications rather than presenting upstream code as original NEXVARY code. Source reference: https://github.com/pagecat/vowifi_gateway/tree/e3719840b93961f933aab3dac8bd2641936e2bcc

The upstream `engine/Dockerfile` uses distro packages and source dependencies, including sysmocom Asterisk/pjproject, panoramisk, pyscard/PCSC, pyserial, pycryptodome, cryptography and mitshell card/CryptoMobile. Its installation commands and several dependencies are not version/hash locked. MIT on the root repository does not replace those component licenses. A future runnable distribution must pin each adopted component, review its official license/source obligations and preserve notices. Software Milenage/Ki support is removed from the staged SWu path; upstream Dockerfiles are not executed or endorsed by this transformation.

## Verification

Create an audit copy from a separately obtained clean checkout at the exact pinned revision:

```bash
python3 server/engine/harden_upstream.py --source /path/to/vowifi_gateway --destination /fresh/path/outside-upstream
```

The command checks the revision, clean tracked/untracked state and hashes of both modified files before writing a fresh private destination. It rejects symlinked tracked files and existing destinations, copies only tracked source files with no executable permissions, preserves the upstream MIT license, and records original source/adapter hashes in `NEXVARY-AUDIT.json`. It does not fetch source, install dependencies or run the copied gateway. Both generated entry points refuse execution before importing upstream dependencies. Diagnostic argument evaluation, APDU tracing, software Milenage/long-term credential options, legacy authentication fallbacks and fabricated identity/authentication defaults are removed. An AMI authentication failure cannot send an empty response as if it were successful.

```bash
python3 -m unittest discover -s server/engine -p 'test_*.py'
```

Tests exercise binary result decoding, actual upstream synchronization conventions, backend/network failures without fabricated outputs, private credential loading, redacted errors, removed log argument evaluation and staged wrappers. They do not require a SIM, ePDG, privileged host, Docker or carrier account. An authorized live Android/UICC AKA attempt and independent protocol evidence remain required.

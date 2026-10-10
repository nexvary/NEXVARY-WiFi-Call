# Audited staging boundary for Phone-as-SIM AKA

This directory contains a fail-closed transient AKA adapter and a **staging-only** hardening transformation for the pinned upstream gateway. It installs no packages, starts no process, changes no firewall/routes and performs no carrier authentication. The generated upstream entry points are deliberately blocked until remaining system/network mutation paths and dependencies have been reviewed. Passing these isolated tests proves no ePDG, IPsec, IMS registration, calling or audio success.

## Broker contract

By default the adapter uses a direct HTTP connection to `127.0.0.1:8787` with a 35-second socket timeout. An explicitly configured private Unix socket provides the same HTTP contract across a reviewed network-namespace boundary, with a 35-second total I/O deadline. Neither transport uses environment proxies, remote URLs, redirects, GET query parameters or automatic retries.

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

### Explicit credential provisioning

First pair the actual phone through the panel and obtain its device UUID from the authenticated devices view. Then, from the reviewed repository checkout on the Ubuntu host, replace `PAIRED_DEVICE_UUID` below with that exact UUID. Run the credential tool as the same dedicated account intended for the future engine adapter; the recommended private configuration is owned by `nexvary-wifi-panel`, rather than requiring a root engine process.

```bash
sudo systemctl stop nexvary-wifi-panel.service
# Required only for an older installation whose state directory is still 0750:
sudo chmod 700 /var/lib/nexvary-wifi-panel
sudo -u nexvary-wifi-panel mkdir -m 700 /var/lib/nexvary-wifi-panel/private-engine
sudo -u nexvary-wifi-panel python3 server/engine/configure_engine.py --configure \
  --state-dir /var/lib/nexvary-wifi-panel \
  --config /var/lib/nexvary-wifi-panel/private-engine/auth.json \
  --device-id PAIRED_DEVICE_UUID
sudo systemctl start nexvary-wifi-panel.service
```

The checkout must be readable by the dedicated account. The CLI requires an existing mode `0700` state directory, existing mode `0600` password/database owned by that state account, a fresh configuration filename and a mode `0700` configuration parent owned by the executing UID. It reads an immutable SQLite snapshot without creating database sidecars and refuses pending WAL/journal transactions; stopping only this owned panel before provisioning lets its transactions close. It verifies the selected device is genuinely paired before creating anything.

The tool generates 32 random bytes of authorization, writes exact `token`/`device_id` JSON with mode `0600`, and stores only its SHA-256 in `engine-token.sha256` with mode `0600` and the panel state's UID/GID. No token is printed or supplied as a command-line argument. Existing files or symlinks are refused, and failure to create the second file removes the newly created first file. It starts/restarts no service and changes no existing password/database/configuration. A process interruption between files requires reviewing the partial fresh credential before retrying; no automatic overwrite or credential reset is provided.

The owned panel loads the hash only when started/restarted; a browser session or pairing does not enable the engine endpoint by itself. A future reviewed adapter process running as the dedicated UID would use `NEXVARY_ENGINE_AUTH_FILE=/var/lib/nexvary-wifi-panel/private-engine/auth.json`. Do not start the staged gateway: its execution remains blocked pending review. For an explicitly authorized different UID using `/etc/nexvary-engine/auth.json`, that directory must already be private and owned by the same executing UID, and that UID must be able to write the panel hash with the panel owner's UID/GID; the dedicated-account configuration above avoids that ownership ambiguity.

### Optional private Unix transport

For an independently reviewed, opt-in Unix relay, set `NEXVARY_AKA_SOCKET` to its absolute socket filename, for example `/run/nexvary-aka/aka.sock`. The adapter requires a mode `0700` parent directory and a mode `0600` Unix socket, both owned by its executing UID. It opens every directory component without following symlinks, rejects relative/traversing paths, checks the socket type, and verifies the connected Linux peer UID before transmitting authorization or challenges. An explicitly configured empty, missing, symlinked, insecure or unauthorized socket fails closed; it never falls back to the host HTTP endpoint.

A full engine network namespace has its own loopback, so its `127.0.0.1:8787` cannot reach the host panel. A private filesystem Unix socket addresses this boundary without publishing the panel or broker on a new network port. A mount namespace must make only the relay's private directory available at the configured path, preserving the dedicated UID and permissions; the same UID must own both ends. Do not use an abstract/public socket, bind-mount the entire host `/run`, or expose the panel state directory solely to reach this socket. Provision the engine credential in its separate private mount. The relay must remain scoped to the existing authenticated AKA endpoint and must not grant arbitrary host HTTP access.

Configuring this transport grants no runtime gateway approval, SIM privilege or live AKA evidence. The staging execution gate remains in place. Real Unix-socket fixture tests require Linux AF_UNIX/SO_PEERCRED access; an executor that denies socket creation cannot verify them, and that limitation must be reported until the mandatory Ubuntu CI tests execute.

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

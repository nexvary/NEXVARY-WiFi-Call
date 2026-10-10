# Ubuntu gateway PoC — preparation and evidence gates

Status: **gateway not deployed, not carrier-tested**. The Android 0.5.0 bridge and authenticated server broker support explicitly consented, temporary AKA sessions. They do not grant the application SIM permissions. The actual shared VPS at `3.65.234.184` runs the panel alongside Outline and FG MTM. The user supplied a successful private network/mount/PID isolation probe with host state unchanged on 2026-10-06. We have no direct SSH access and have not executed a gateway on this VPS.

## Read-only first

On the actual Ubuntu 24.04 server:

```bash
bash server/preflight.sh
# Optional: a known carrier ePDG hostname, without an IMSI or other SIM identifier
bash server/preflight.sh --epdg epdg.example.net
# Optional external DNS query to observe public IPv4
bash server/preflight.sh --public-ip
bash server/install.sh --plan
```

Preflight inventories RAM/swap, CPU, disk/inodes, Docker/Compose, listening ports, firewall, existing services/systemd, IPv4/IPv6/routes, DNS and TUN/XFRM availability. Permission failures are explicit. It performs no package install, configuration change, port opening, swap allocation or SIM operation. Raw inventory includes host addresses/service names and must be reviewed before sharing. A completed script with missing checks is not deployment approval.

## 1 GiB host plan

Use one line initially. Build Asterisk/engine and WebUI on a separate machine; transfer an immutable reviewed image rather than compile on the 1 GiB VPS. Prefer the upstream native control plane to a second privileged container; bind management to localhost and reach it through an SSH tunnel/private network. Avoid Grafana/Prometheus/eSIM services in the first PoC. Measure memory under registration and a real call; no resource measurements have been taken on this server.

If preflight shows insufficient swap, review a 2–4 GiB swapfile on a supported filesystem after checking free disk and existing swap/fstab. Do not create duplicate swap or overwrite an existing file. No supplied script changes swap or fstab. Do not change existing SIP, web, Docker, PC/SC or firewall services without first recording their configuration and conflicts. Management is not public by default; SIP/RTP endpoints require a separately reviewed access policy.

## Phone-as-SIM gate before buying a reader

1. Install the APK on the real Android phone and choose the actual subscription.
2. Grant the ordinary phone-state permission, then inspect Phone-as-SIM in Diagnostics.
3. Record capability, device/API level, application signing identity, carrier scope and UTC time. Carrier privileges depend on the application certificate/USIM access rules; ordinary `READ_PHONE_STATE` is not sufficient to authorize AKA.
4. If privileges are missing, record that limitation. Do not use root, hidden APIs, RIL patches or platform keys to bypass it. A carrier-approved application or an external authorized reader is the next practical option.
5. If privileges are present, a subsequent authorized live test must invoke `getIccAuthentication(APPTYPE_USIM, AUTHTYPE_EAP_AKA, challenge)` for the selected subscription. A privilege check alone is **not AKA verified**. Treat null/error/AUTS distinctly; no fabricated success.

The foreground phone adapter and private engine broker are implemented with authenticated enrollment, selected-subscription binding, strict RAND/AUTN parsing, short challenge deadlines and replay/rate controls. The selected phone currently reports no carrier privilege for this application; actual AKA remains unverified. See [PHONE-AKA-BRIDGE.md](PHONE-AKA-BRIDGE.md) for the implemented contract and [PHONE-AS-SIM-OPTIONS.md](PHONE-AS-SIM-OPTIONS.md) for authorized alternatives. Never extract Ki/long-term SIM secrets. Never log or persist authentication responses, CK/IK, session keys, PINs or full challenge material. No arbitrary APDU/proxy endpoint is permitted in the consumer build.

Android reference: [TelephonyManager](https://developer.android.com/reference/android/telephony/TelephonyManager#getIccAuthentication(int,%20int,%20java.lang.String)), [carrier privilege rules](https://source.android.com/docs/core/connect/uicc).

## Upstream adoption gates

First candidate: [pagecat/vowifi_gateway](https://github.com/pagecat/vowifi_gateway), pinned audit revision `e3719840b93961f933aab3dac8bd2641936e2bcc` (checked 2026-10-05). To stage sources only:

```bash
bash server/install.sh --prepare-source
```

This creates a marked private `server/work/upstream` checkout and does **not** execute upstream scripts. Defaults in that repository require review before any use:

- Its README describes Ki/OPc credentials. NEXVARY permits only on-SIM authentication; reject software-Milenage `--ki/--op/--opc` configuration.
- `engine/swu_ike.py` contains fallback sample IMSI/RES/CK/IK values when a reader/server fails. Replace those branches with explicit hard failure before use; synthetic values must never count as carrier evidence.
- `engine/ami_usim.py` logs AKA result/key values; SWu prints similar material and decryption diagnostics. Suppress key logging at the source and verify failure/success logs contain no key material before enabling persistent logs or exports.
- No Android bridge exists in the original upstream pin. NEXVARY's staged adapter uses its own authenticated temporary bridge; PC/SC support alone does not imply Phone-as-SIM support. Both EAP-AKA and IMS-AKA must use the authorized chosen backend. Staged entry points remain blocked until the remaining system mutation and dependency review is complete.
- Its installer can install Docker, rebuild/version-lock PC/SC components, build images, enable autostart and start services. Never run it blindly on the existing host. Native control default binding must be constrained before deployment.
- Audit every bundled dependency and preserve required license notices/source obligations. The top-level MIT license does not relicense Asterisk, PC/SC or other components.

Audit source links: [SWu client](https://github.com/pagecat/vowifi_gateway/blob/e3719840b93961f933aab3dac8bd2641936e2bcc/engine/swu_ike.py), [IMS-AKA bridge](https://github.com/pagecat/vowifi_gateway/blob/e3719840b93961f933aab3dac8bd2641936e2bcc/engine/ami_usim.py), [upstream installer](https://github.com/pagecat/vowifi_gateway/blob/e3719840b93961f933aab3dac8bd2641936e2bcc/install.sh).

## Independent verification milestones

| Milestone | Required observation | Does not imply |
|---|---|---|
| SIM detected | Authorized active subscription or reader detection | AKA available |
| AKA verified | Real authorized challenge response, result retained only transiently | ePDG reachable |
| ePDG discovered/reached | Actual scoped DNS/reachability result | SWu authenticated |
| SWu/IPsec established | Negotiated authenticated tunnel, peer, expiry | IMS registration |
| IMS registered | Actual successful REGISTER response and expiry | Calling works |
| Outbound verified | Real outbound call connected | Inbound works |
| Inbound verified | Independently received/answered call | Outbound works |
| Audio verified | Both directions heard/observed in a real call | Production readiness |

Each milestone carries timestamp, device/application revision, carrier and chosen subscription scope. Store redacted outcomes rather than raw SIP captures or key material. A running Docker container, open port or systemd service establishes none of these milestones.

`health-check.sh` reports host/runtime inventory only. `uninstall.sh --plan` describes reversal; `--archive-source` moves only marked prepared sources to a dated backup without deleting data. These scripts own no installed service, so they never stop unrelated processes or purge Docker volumes/images, packages, swap or firewall rules.

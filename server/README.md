# NEXVARY WiFi Call server

## Admin panel

The admin panel supports password login, live host resources, one-use phone/QR pairing, sanitized diagnostic reports, revocation and explicitly consented transient AKA sessions. The Android 0.5.0 app uses the same contract. No VoWiFi protocol engine has been deployed; the eight carrier stages remain untested. See [phone/panel pairing](../docs/GATEWAY-PAIRING.md) and [temporary AKA bridge](docs/PHONE-AKA-BRIDGE.md).

```bash
bash server/preflight.sh
sudo bash server/install-panel.sh --install
```

See [admin panel installation](docs/ADMIN-PANEL.md) for SSH access and service checks.

## Gateway preparation


These tools prepare the next milestone after the Android APK. No gateway has been installed or verified.

```bash
bash server/preflight.sh               # read-only actual-host inventory
bash server/install.sh --plan          # safe default; explains gates
bash server/install.sh --prepare-source # download pinned source for audit only
bash server/health-check.sh            # host/runtime checks, not carrier verification
bash server/uninstall.sh --plan        # safe default
bash server/uninstall.sh --archive-source # preserve prepared sources in a dated archive
```

Read [Gateway PoC gates](docs/GATEWAY-POC.md) and [open-source/license assessment](docs/OPEN-SOURCE-ASSESSMENT.md) before deployment. `config/gateway.env.example` documents a localhost-only proposal; scripts never source arbitrary environment files or SIM secrets.

The next independent network diagnostic is a [single initial ePDG IKE exchange](docs/EPDG-PROBE.md). It uses the standard library and no upstream runtime. Print its plan with `python3 server/engine/epdg_probe.py`; actual traffic requires an explicit reviewed public endpoint. A response is unauthenticated and never verifies AKA/IPsec/IMS. The read-only source audit is `python3 server/engine/audit_gateway.py --source server/work/upstream`; a valid inventory returns code 2 while execution remains blocked.

Ubuntu target: 24.04, 2 vCPU, 1 GiB RAM, 40 GiB disk. The actual shared VPS has 2 GiB swap, working ePDG DNS resolution and a successful temporary namespace isolation probe. The current phone reports no carrier privileges for this app; actual AKA is unverified. Start with one SIM and build heavy components off-server. Preparation scripts do not alter existing services, swap, firewall or system packages. Read [isolation preparation](docs/GATEWAY-ISOLATION.md) and [authorized SIM access options](docs/PHONE-AS-SIM-OPTIONS.md).

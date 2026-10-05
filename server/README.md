# NEXVARY WiFi Call server

## Admin panel

The admin panel supports password login, live host resources, one-use phone pairing, sanitized diagnostic reports and revocation. The Android app uses the same contract. No VoWiFi protocol engine has been deployed; the eight carrier stages remain untested. See [phone/panel pairing](../docs/GATEWAY-PAIRING.md).

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

Ubuntu target: 24.04, 2 vCPU, 1 GiB RAM, 40 GiB disk. The actual server inventory and phone/SIM privilege result remain required. Start with one SIM and build heavy components off-server. Nothing here alters services, swap, firewall or system packages.

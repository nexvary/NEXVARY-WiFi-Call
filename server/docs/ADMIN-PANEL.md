# NEXVARY private administration panel

The panel displays host information and sanitized reports from explicitly paired Android phones. It permits pairing and revocation; it does not execute gateway operations. **It is not a deployed VoWiFi gateway**: an HTTP server, SIM capability check, running service or green host check establishes no AKA, ePDG/IPsec, IMS registration, call or audio success.

## Install on the actual Ubuntu server

Target: Ubuntu 24.04 with Python 3 and systemd already installed. No Python packages, Docker, firewall configuration or existing services are changed. First run the read-only host preflight and inspect existing listeners:

```bash
bash server/preflight.sh
bash server/install-panel.sh --plan
sudo bash server/install-panel.sh --install
```

Use an interactive SSH terminal. Installation prompts for the panel password without a command-line argument. Do not place the password in shell history, an environment file or diagnostic exports. The app stores its password hash in private persistent state, not a plaintext password.

The installer:

- Refuses an existing application path, state path, systemd unit, user/group or occupied localhost port. For an existing owned installation, use the separate verified update procedure below.
- Copies `server/panel/app.py`, `phone_store.py` and `index.html` to `/opt/nexvary-wifi-panel`.
- Creates an isolated `nexvary-wifi-panel` system user with no login shell; it is not placed in sudo or Docker groups.
- Keeps persistent state in `/var/lib/nexvary-wifi-panel`, owned by that user and inaccessible to other users.
- Starts only `nexvary-wifi-panel.service` on `127.0.0.1:8787`.
- Applies systemd filesystem, privilege, kernel and process restrictions, with a 128 MiB memory limit and 32-task limit.

Application code and the systemd unit are root-owned. The service can write only its state directory and private temporary files. Some privileged host information will therefore be unavailable; report that limitation rather than escalating the panel. Never grant the service access to raw SIM secrets, Docker administration, arbitrary shell commands or root.

If installation fails, read the exact error and inspect the named staging or installed paths. The installer does not overwrite existing data to recover automatically. Use the owned archive procedure only after verifying ownership. Fresh installation never overwrites existing paths; the separate updater verifies ownership before changing code. No successful server installation is claimed until the service and panel have been checked on the real host.

## Access through an SSH tunnel

From your computer, replacing `USER@SERVER` with the server's authorized SSH account/address:

```bash
ssh -N -L 8787:127.0.0.1:8787 USER@SERVER
```

Then open **http://127.0.0.1:8787** in your local browser and sign in with the password chosen during installation. The tunnel encrypts the remote connection. Keep the listener on localhost; do not open public port 8787 or bind it to all interfaces. No public DNS name or TLS reverse proxy is needed for this first private panel.

The same local and remote port is required by the panel's strict HTTP Host validation. If local port 8787 is already used, close that local listener or review a separately configured panel port. Closing SSH closes access. Do not share tunnel access or panel credentials publicly.

## Verify without claiming carrier readiness

```bash
sudo systemctl status --no-pager nexvary-wifi-panel.service
sudo journalctl -u nexvary-wifi-panel.service --since '10 minutes ago' --no-pager
ss -ltn 'sport = :8787'
```

Confirm the listener is `127.0.0.1:8787`, sign-in works through the tunnel, failed sign-in does not reveal state, and the panel identifies untested carrier stages honestly. Host addresses and service names may be sensitive; review/redact any diagnostic output before sharing. No authentication/key material belongs in logs.

Actual carrier progress remains the independent evidence sequence in [GATEWAY-POC.md](GATEWAY-POC.md). Test Phone-as-SIM on the real Android phone/SIM before choosing a reader or implementing the gateway AKA adapter.

## Stop or uninstall only this panel

To stop the service temporarily:

```bash
sudo systemctl stop nexvary-wifi-panel.service
```

To inspect removal, then archive the owned install:

```bash
bash server/uninstall-panel.sh --plan
sudo bash server/uninstall-panel.sh --archive-owned
```

The archive action validates the installation marker and unchanged unit checksum, stops/disables only the owned panel service, and moves the code/unit into a dated root-private archive under `/opt`. It preserves the password state and service account and does not delete application data. Other services, packages, gateway sources, Docker objects and firewall rules remain untouched.

A reinstall will deliberately refuse the preserved state/user. Review an explicit migration or recovery plan before replacing them; this initial installer provides no destructive purge or automatic credential reset.

## Installer verification

`server/panel/install-smoke.py` is restricted to disposable GitHub-hosted Ubuntu 24.04 Actions runners. It executes the real installer through a PTY, supplies a random password twice without printing it, checks actual systemd activation/unprivileged ownership/loopback listener, authenticates the health and inventory endpoints, verifies an actual owned upgrade retains the original password, phone report and bearer authorization, and verifies the owned archive preserves password and phone state. Credentials, cookies, hashes and captured installer output are withheld from CI logs.

The smoke script refuses local execution and existing installation/user/state paths. Syntax and this local refusal can be checked without installing anything. Only a successful `installer-smoke` CI job validates actual Ubuntu installation; it does not validate the user's server or any carrier gateway. Real server preflight and independent AKA/IMS/call/audio evidence are still required.


## Optional HTTPS phone-report endpoint

For a remote Android phone, configure a dedicated HTTPS DNS origin and reverse proxy separately, preserving existing web services. The initial install can bind its allowlisted public origin:

```bash
sudo bash server/install-panel.sh --install --public-origin https://panel.example.org
```

Only an ASCII HTTPS DNS origin with an optional valid port is accepted; paths, credentials, query strings and fragments are rejected. The Python service still binds `127.0.0.1:8787`. With a public origin configured, use the HTTPS origin for browser administration: secure cookies will not authenticate plain HTTP tunnel requests. This option configures origin validation and secure cookies; it does not install a proxy, issue a certificate, alter DNS, open firewall ports or verify the remote endpoint. Review the proxy configuration supplied with this project before activating it on the real host.

Pairing codes expire after ten minutes and are single-use. Only credential hashes and a strict report schema are stored in private SQLite state; long-term SIM secrets, SIM identities, phone numbers, carrier identifiers, gateway verification flags and device-supplied timestamps are rejected. Unpairing removes the device's authorization. A report of Android carrier privilege is a capability preflight, not live AKA success.


## Update an existing owned installation

```bash
bash server/update-panel.sh --plan
sudo bash server/update-panel.sh --update
# Optional: configure a separately reviewed HTTPS proxy origin during the update
sudo bash server/update-panel.sh --update --public-origin https://panel.example.org
```

The updater checks the root-owned application marker, unchanged systemd unit checksum, actual unit path and absence of symlinked installation paths. It stages `app.py`, `phone_store.py` and `index.html`, archives the old code/unit, then restarts only this panel. A failed restart or health check restores the previous code/unit and previous running state. Password hashes and the phone SQLite database remain in `/var/lib/nexvary-wifi-panel`; they are never copied into the code archive or rewritten by the update script. Existing HTTPS origin settings are preserved when the optional origin argument is omitted.

Browser sessions live only in memory, so sign in again with the same password after updating. Paired phone credentials and sanitized reports remain persistent. Old code/unit archives remain root-private for review and recovery. The updater refuses unfamiliar service commands or ownership changes rather than replacing unrelated services.

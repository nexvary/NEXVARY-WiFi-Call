#!/usr/bin/env bash
# Ubuntu 24.04: isolated localhost-only NEXVARY host-inventory panel.
# This installs no VoWiFi gateway or protocol engine and changes no firewall rules.
set -euo pipefail
umask 077
base_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
app_dir=/opt/nexvary-wifi-panel
state_dir=/var/lib/nexvary-wifi-panel
service_user=nexvary-wifi-panel
unit_file=/etc/systemd/system/nexvary-wifi-panel.service
usage() { printf 'Usage: sudo bash server/install-panel.sh --install\n       bash server/install-panel.sh --plan\n'; }
[[ $# -le 1 ]] || { usage >&2; exit 2; }
case "${1:---plan}" in
  --plan|--help)
    cat <<'PLAN'
Install plan (no changes performed):
  Require Ubuntu 24.04, Python 3 and systemd already installed.
  Refuse existing app/state/unit/user; preserve all other services and firewall.
  Copy panel app.py and index.html into /opt/nexvary-wifi-panel.
  Prompt interactively for a password; keep its hash in private persistent state.
  Create dedicated unprivileged nexvary-wifi-panel user and hardened systemd unit.
  Enable/start nexvary-wifi-panel.service on 127.0.0.1:8787 only.
  Access via SSH tunnel: ssh -N -L 8787:127.0.0.1:8787 USER@SERVER
  Open http://127.0.0.1:8787 locally. This is host inventory, not a working gateway.
To apply: sudo bash server/install-panel.sh --install
PLAN
    exit 0 ;;
  --install) ;;
  *) usage >&2; exit 2 ;;
esac
[[ $EUID == 0 ]] || { printf 'Run --install with sudo.\n' >&2; exit 1; }
[[ -t 0 ]] || { printf 'An interactive terminal is required to initialize the password.\n' >&2; exit 1; }
[[ -r /etc/os-release ]] || { printf 'Cannot identify operating system.\n' >&2; exit 1; }
# /etc/os-release is a trusted operating-system file, not an application config.
. /etc/os-release
[[ ${ID:-} == ubuntu && ${VERSION_ID:-} == 24.04 ]] || { printf 'This installer requires Ubuntu 24.04.\n' >&2; exit 1; }
[[ -x /usr/bin/python3 ]] || { printf '/usr/bin/python3 required; install separately.\n' >&2; exit 1; }
for executable in systemctl useradd getent install mktemp sha256sum; do
  command -v "$executable" >/dev/null || { printf 'Missing required tool: %s. Install separately.\n' "$executable" >&2; exit 1; }
done
[[ -d /run/systemd/system ]] || { printf 'systemd is not running on this host.\n' >&2; exit 1; }
[[ -f "$base_dir/panel/app.py" && -f "$base_dir/panel/index.html" ]] || { printf 'Panel source files are missing.\n' >&2; exit 1; }
for existing in "$app_dir" "$state_dir" "$unit_file"; do
  [[ ! -e "$existing" && ! -L "$existing" ]] || { printf 'Refusing existing installation path: %s\n' "$existing" >&2; exit 1; }
done
if getent passwd "$service_user" >/dev/null || getent group "$service_user" >/dev/null; then
  printf 'Refusing existing user/group %s; inspect ownership before continuing.\n' "$service_user" >&2; exit 1
fi
if systemctl cat nexvary-wifi-panel.service >/dev/null 2>&1; then
  printf 'Refusing an existing systemd unit with this name.\n' >&2; exit 1
fi
# Binding probe closes immediately; no daemon or firewall change. A race still fails at startup.
/usr/bin/python3 - <<'PY'
import socket
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(('127.0.0.1', 8787))
PY
stage_app=$(mktemp -d /opt/.nexvary-wifi-panel.XXXXXXXX)
stage_state=$(mktemp -d /var/lib/.nexvary-wifi-panel.XXXXXXXX)
trap 'printf "Installation interrupted. Private staging paths, if still present: %s %s\n" "$stage_app" "$stage_state" >&2' ERR
install -m 644 "$base_dir/panel/app.py" "$stage_app/app.py"
install -m 644 "$base_dir/panel/index.html" "$stage_app/index.html"
/usr/bin/python3 "$stage_app/app.py" --init-password --state-dir "$stage_state"
useradd --system --user-group --home-dir "$state_dir" --no-create-home --shell /usr/sbin/nologin "$service_user"
chown -R "$service_user:$service_user" "$stage_state"
chmod 750 "$stage_state"
chmod 755 "$stage_app"
printf 'NEXVARY admin panel install v1\n' > "$stage_app/.nexvary-panel-owned"
mv -- "$stage_app" "$app_dir"
mv -- "$stage_state" "$state_dir"
cat > "$unit_file" <<'UNIT'
# NEXVARY-owned panel unit v1. No VoWiFi gateway is started by this service.
[Unit]
Description=NEXVARY WiFi Call read-only host inventory panel
After=network.target

[Service]
Type=simple
User=nexvary-wifi-panel
Group=nexvary-wifi-panel
WorkingDirectory=/opt/nexvary-wifi-panel
ExecStart=/usr/bin/python3 /opt/nexvary-wifi-panel/app.py --state-dir /var/lib/nexvary-wifi-panel --port 8787
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/nexvary-wifi-panel
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ProtectKernelLogs=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK
CapabilityBoundingSet=
AmbientCapabilities=
MemoryMax=128M
TasksMax=32

[Install]
WantedBy=multi-user.target
UNIT
chmod 644 "$unit_file"
sha256sum "$unit_file" | awk '{print $1}' > "$app_dir/.nexvary-panel-unit-sha256"
systemctl daemon-reload
systemctl enable --now nexvary-wifi-panel.service
systemctl is-active --quiet nexvary-wifi-panel.service
trap - ERR
printf 'Panel service started on localhost only. No gateway or carrier path has been verified.\n'
printf 'Tunnel: ssh -N -L 8787:127.0.0.1:8787 USER@SERVER\n'
printf 'Then open http://127.0.0.1:8787 on your computer.\n'

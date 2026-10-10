#!/usr/bin/env bash
# Stops only a verified owned panel; archives source/unit, preserves password state and user.
set -euo pipefail
umask 077
app_dir=/opt/nexvary-wifi-panel
state_dir=/var/lib/nexvary-wifi-panel
unit_file=/etc/systemd/system/nexvary-wifi-panel.service
usage() { printf 'Usage: bash server/uninstall-panel.sh --plan\n       sudo bash server/uninstall-panel.sh --archive-owned\n'; }
[[ $# -le 1 ]] || { usage >&2; exit 2; }
case "${1:---plan}" in
  --plan|--help)
    printf 'No changes performed. --archive-owned stops/disables only the verified owned panel.\n'
    printf 'Code and unit are archived. State/password hash and unprivileged user are preserved.\n'
    printf 'No gateway, other services, packages, firewall rules or Docker data are changed.\n'
    exit 0 ;;
  --archive-owned) ;;
  *) usage >&2; exit 2 ;;
esac
[[ $EUID == 0 ]] || { printf 'Run --archive-owned with sudo.\n' >&2; exit 1; }
[[ -d "$app_dir" && ! -L "$app_dir" && -f "$app_dir/.nexvary-panel-owned" && -f "$app_dir/.nexvary-panel-unit-sha256" ]] || { printf 'Owned panel marker missing; refusing.\n' >&2; exit 1; }
[[ $(cat "$app_dir/.nexvary-panel-owned") == 'NEXVARY admin panel install v1' ]] || { printf 'Ownership marker mismatch; refusing.\n' >&2; exit 1; }
[[ -f "$unit_file" && ! -L "$unit_file" ]] || { printf 'Owned unit file missing; refusing.\n' >&2; exit 1; }
expected_sha=$(cat "$app_dir/.nexvary-panel-unit-sha256")
actual_sha=$(sha256sum "$unit_file" | awk '{print $1}')
[[ "$expected_sha" == "$actual_sha" ]] || { printf 'Unit changed since installation; inspect it before uninstalling.\n' >&2; exit 1; }
active_unit=$(systemctl show -p FragmentPath --value nexvary-wifi-panel.service)
[[ "$active_unit" == "$unit_file" ]] || { printf 'Active systemd unit is not the owned unit; refusing.\n' >&2; exit 1; }
backup="/opt/nexvary-wifi-panel.archived.$(date -u +%Y%m%dT%H%M%SZ)"
[[ ! -e "$backup" ]] || { printf 'Archive path already exists; refusing.\n' >&2; exit 1; }
systemctl disable --now nexvary-wifi-panel.service
mkdir -m 700 "$backup"
mv -- "$unit_file" "$backup/nexvary-wifi-panel.service"
mv -- "$app_dir" "$backup/app"
systemctl daemon-reload
printf 'Panel stopped and archived at %s\n' "$backup"
printf 'Persistent state at %s and service user retained. No data deleted.\n' "$state_dir"

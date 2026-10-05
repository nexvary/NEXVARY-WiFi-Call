#!/usr/bin/env bash
# Upgrade only a verified owned panel, preserving private password/phone state.
set -euo pipefail
umask 077
base_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
app_dir=/opt/nexvary-wifi-panel
state_dir=/var/lib/nexvary-wifi-panel
unit_file=/etc/systemd/system/nexvary-wifi-panel.service
service=nexvary-wifi-panel.service
usage() { printf 'Usage: sudo bash server/update-panel.sh --update [--public-origin https://panel.example.org]\n       bash server/update-panel.sh --plan\n'; }
action=--plan
public_origin=''
action_seen=false
while (($#)); do
  case "$1" in
    --update|--plan|--help) $action_seen && { usage >&2; exit 2; }; action=$1; action_seen=true; shift ;;
    --public-origin) [[ $# -ge 2 && -z "$public_origin" ]] || { usage >&2; exit 2; }; public_origin=$2; shift 2 ;;
    *) usage >&2; exit 2 ;;
  esac
done
if [[ -n "$public_origin" ]]; then
  /usr/bin/python3 - "$public_origin" <<'ORIGIN'
import re
import sys
from urllib.parse import urlsplit
origin = sys.argv[1]
match = re.fullmatch(r'https://([A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)(?::([0-9]{1,5}))?', origin)
if not match:
    raise SystemExit('Public origin must be an HTTPS DNS origin without a path or credentials.')
host = match.group(1)
if any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in host.split('.')):
    raise SystemExit('Invalid DNS name in public origin.')
port = match.group(2)
if port and not 1 <= int(port) <= 65535:
    raise SystemExit('Invalid public origin port.')
parsed = urlsplit(origin)
if parsed.scheme != 'https' or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
    raise SystemExit('Invalid public origin.')
ORIGIN
fi
if [[ "$action" == --plan || "$action" == --help ]]; then
  printf 'No changes performed. --update verifies the owned root-controlled installation.\n'
  printf 'New code is staged; old code/unit archived; password and phone database stay in place.\n'
  printf 'Only this panel service is restarted; failed health check rolls back code/unit.\n'
  printf 'Existing public origin is preserved unless --public-origin supplies a validated HTTPS origin.\n'
  exit 0
fi
[[ $EUID == 0 ]] || { printf 'Run --update with sudo.\n' >&2; exit 1; }
for path in "$app_dir" "$state_dir" "$unit_file"; do
  [[ -e "$path" && ! -L "$path" ]] || { printf 'Missing or symlinked install path; refusing.\n' >&2; exit 1; }
done
for path in "$app_dir" "$unit_file" "$app_dir/.nexvary-panel-owned" "$app_dir/.nexvary-panel-unit-sha256"; do
  [[ ! -L "$path" && $(stat -c %u "$path") == 0 ]] || { printf 'Install ownership is not root-controlled; refusing.\n' >&2; exit 1; }
  permissions=$(stat -c %a "$path")
  (( (8#$permissions & 8#022) == 0 )) || { printf 'Install path is writable by non-root accounts; refusing.\n' >&2; exit 1; }
done
[[ $(cat "$app_dir/.nexvary-panel-owned") == 'NEXVARY admin panel install v1' ]] || { printf 'Ownership marker mismatch; refusing.\n' >&2; exit 1; }
[[ $(cat "$app_dir/.nexvary-panel-unit-sha256") == $(sha256sum "$unit_file" | awk '{print $1}') ]] || { printf 'Unit changed since installation; inspect before updating.\n' >&2; exit 1; }
[[ $(systemctl show -p FragmentPath --value "$service") == "$unit_file" ]] || { printf 'Active unit path is not the owned unit; refusing.\n' >&2; exit 1; }
for source in app.py phone_store.py index.html; do
  [[ -f "$base_dir/panel/$source" && ! -L "$base_dir/panel/$source" ]] || { printf 'Required source missing/symlinked: %s\n' "$source" >&2; exit 1; }
done
stage_app=$(mktemp -d /opt/.nexvary-wifi-panel.update.XXXXXXXX)
stage_unit=$(mktemp /etc/systemd/system/.nexvary-wifi-panel.update.XXXXXXXX)
for source in app.py phone_store.py index.html; do install -m 644 "$base_dir/panel/$source" "$stage_app/$source"; done
/usr/bin/python3 - "$stage_app" <<'CHECK'
from pathlib import Path
import sys
for name in ('app.py', 'phone_store.py'):
    source = Path(sys.argv[1]) / name
    compile(source.read_text(), str(source), 'exec')
CHECK
install -m 644 "$unit_file" "$stage_unit"
/usr/bin/python3 - "$stage_unit" "$public_origin" <<'ARGS'
from pathlib import Path
import re
import sys
path = Path(sys.argv[1])
text = path.read_text()
base = 'ExecStart=/usr/bin/python3 /opt/nexvary-wifi-panel/app.py --state-dir /var/lib/nexvary-wifi-panel --port 8787'
lines = [line for line in text.splitlines() if line.startswith('ExecStart=')]
if len(lines) != 1 or not re.fullmatch(re.escape(base) + r'(?: --public-origin https://[A-Za-z0-9.:-]+)?', lines[0]):
    raise SystemExit('Refusing unfamiliar service command.')
if sys.argv[2]:
    path.write_text(text.replace(lines[0], base + ' --public-origin ' + sys.argv[2]))
ARGS
printf 'NEXVARY admin panel install v1\n' > "$stage_app/.nexvary-panel-owned"
sha256sum "$stage_unit" | awk '{print $1}' > "$stage_app/.nexvary-panel-unit-sha256"
chmod 755 "$stage_app"
backup="/opt/nexvary-wifi-panel.updated.$(date -u +%Y%m%dT%H%M%SZ)"
[[ ! -e "$backup" ]] || { printf 'Archive exists; refusing.\n' >&2; exit 1; }
mkdir -m 700 "$backup"
install -m 600 "$unit_file" "$backup/nexvary-wifi-panel.service"
old_active=false
if systemctl is-active --quiet "$service"; then old_active=true; fi
old_archived=false
rollback() {
  local rc=$?
  trap - ERR
  printf 'Update failed; restoring the previous owned panel code/unit.\n' >&2
  systemctl stop "$service" || true
  if $old_archived; then
    if [[ -d "$app_dir" ]]; then mv -- "$app_dir" "$backup/failed-new-app"; fi
    mv -- "$backup/app" "$app_dir"
  fi
  install -m 644 "$backup/nexvary-wifi-panel.service" "$stage_unit"
  mv -- "$stage_unit" "$unit_file"
  systemctl daemon-reload || true
  if $old_active; then systemctl start "$service" || printf 'Previous service failed to restart; inspect systemd.\n' >&2; fi
  printf 'Private state was preserved. Review archive: %s\n' "$backup" >&2
  exit "$rc"
}
trap rollback ERR
systemctl stop "$service"
mv -- "$app_dir" "$backup/app"
old_archived=true
mv -- "$stage_app" "$app_dir"
mv -- "$stage_unit" "$unit_file"
systemctl daemon-reload
systemctl start "$service"
/usr/bin/python3 - <<'HEALTH'
import json
import time
import urllib.error
import urllib.request
deadline = time.monotonic() + 20
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=3) as response:
            result = json.load(response)
        if result == {'panel': 'ok', 'gateway_verified': False}:
            break
    except (OSError, ValueError, urllib.error.URLError):
        pass
    time.sleep(0.2)
else:
    raise SystemExit('Updated panel health check failed.')
HEALTH
systemctl is-active --quiet "$service"
trap - ERR
printf 'Owned panel updated; prior code/unit archived at %s. Private state retained.\n' "$backup"
printf 'No gateway or carrier success has been established.\n'

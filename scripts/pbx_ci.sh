#!/usr/bin/env bash
# Disposable-runner-only synthetic test. Does not edit /etc or restart services.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v asterisk >/dev/null
python3 -c 'import pylibsrtp'
test -r /usr/share/asterisk/documentation/core-en_US.xml
module_file=$(dpkg-query -L asterisk-modules | awk '/\/res_pjsip\.so$/ && !found { path=$0; found=1 } END { print path }')
test -n "$module_file"
test -r "$module_file"
module_directory=$(dirname "$module_file")
mkdir -p pbx-evidence
rm -f pbx-evidence/integration.json
runtime=$(mktemp -d)
pbx_pid=""
cleanup() {
  if [[ -n "$pbx_pid" ]]; then
    kill "$pbx_pid" 2>/dev/null || true
    wait "$pbx_pid" 2>/dev/null || true
  fi
  rm -rf "$runtime"
}
trap cleanup EXIT
python3 server/deploy/pbx/generate.py --output "$runtime/config"
mkdir -p "$runtime/tls" "$runtime/run" "$runtime/log" "$runtime/spool" "$runtime/db"
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 1 \
  -subj '/CN=127.0.0.1' -addext 'subjectAltName=IP:127.0.0.1' \
  -keyout "$runtime/tls/privkey.pem" -out "$runtime/tls/fullchain.pem" 2>/dev/null
chmod 600 "$runtime/tls/privkey.pem"
RUNTIME="$runtime" AST_MODULE_DIRECTORY="$module_directory" python3 - <<'PY'
import os
from pathlib import Path
r=Path(os.environ['RUNTIME'])
p=r/'config/pjsip.conf'
p.write_text(p.read_text().replace('/etc/asterisk/tls/',str(r/'tls')+'/'))
(r/'config/asterisk.conf').write_text(f'''[directories]
astetcdir => {r}/config
astmoddir => {os.environ['AST_MODULE_DIRECTORY']}
astvarlibdir => /var/lib/asterisk
astdbdir => {r}/db
astkeydir => {r}/tls
astdatadir => /usr/share/asterisk
astagidir => {r}/spool
astspooldir => {r}/spool
astrundir => {r}/run
astlogdir => {r}/log
[options]
verbose = 0
debug = 0
''')
PY
asterisk -f -C "$runtime/config/asterisk.conf" > "$runtime/asterisk.log" 2>&1 &
pbx_pid=$!
for attempt in $(seq 1 40); do
  if asterisk -C "$runtime/config/asterisk.conf" -rx 'pjsip show transports' 2>/dev/null | grep -q 'secure-tls'; then
    break
  fi
  if ! kill -0 "$pbx_pid" 2>/dev/null; then
    cat "$runtime/asterisk.log"
    exit 1
  fi
  sleep 0.5
done
# Print module/version information, never config/account files or SDP debug logs.
asterisk -C "$runtime/config/asterisk.conf" -rx 'core show version' | tee pbx-evidence/version.txt
asterisk -C "$runtime/config/asterisk.conf" -rx 'module show like res_srtp' | tee pbx-evidence/srtp-module.txt
python3 scripts/pbx_integration.py --ca "$runtime/tls/fullchain.pem" --accounts "$runtime/config/accounts.json" | tee pbx-evidence/integration.json

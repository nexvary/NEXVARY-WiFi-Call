#!/usr/bin/env bash
# Disposable Ubuntu runner only; separate coturn process, no host service changes.
set -euo pipefail
cd "$(dirname "$0")/../../.."
command -v turnserver >/dev/null
runtime=$(mktemp -d)
turn_pid=""
cleanup() {
  if [[ -n "$turn_pid" ]]; then kill "$turn_pid" 2>/dev/null || true; wait "$turn_pid" 2>/dev/null || true; fi
  rm -rf "$runtime"
}
trap cleanup EXIT
mkdir -p turn-evidence
rm -f turn-evidence/integration.json
python3 server/deploy/turn/generate.py --output "$runtime/config" --realm localhost \
  --peer 127.0.0.1 --verified-pbx --verified-private-peer
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 1 -subj '/CN=127.0.0.1' \
  -addext 'subjectAltName=IP:127.0.0.1' -keyout "$runtime/key.pem" -out "$runtime/cert.pem" 2>/dev/null
chmod 600 "$runtime/key.pem"
RUNTIME="$runtime" python3 - <<'PY'
import os
from pathlib import Path
r=Path(os.environ['RUNTIME']);p=r/'config/turnserver.conf'
p.write_text(p.read_text().replace('/etc/nexvary-turn/tls/fullchain.pem',str(r/'cert.pem'))
 .replace('/etc/nexvary-turn/tls/privkey.pem',str(r/'key.pem'))
 .replace('/run/nexvary-turn/turnserver.pid',str(r/'turnserver.pid')))
PY
turnserver -c "$runtime/config/turnserver.conf" > "$runtime/turn.log" 2>&1 &
turn_pid=$!
RUNTIME="$runtime" python3 - <<'PY'
import os,socket,ssl,time
from pathlib import Path
r=Path(os.environ['RUNTIME']);ctx=ssl.create_default_context(cafile=str(r/'cert.pem'))
for attempt in range(60):
    try:
        with ctx.wrap_socket(socket.create_connection(('127.0.0.1',5349),timeout=1),server_hostname='127.0.0.1'): break
    except OSError: time.sleep(.25)
else: raise RuntimeError('Disposable coturn TLS listener did not become ready')
PY
dpkg-query -W -f='${Package} ${Version}\n' coturn | tee turn-evidence/version.txt
PYTHONPATH=server python3 server/deploy/turn/integration.py --secret-file "$runtime/config/auth-secret" \
  --ca "$runtime/cert.pem" --evidence turn-evidence/integration.json

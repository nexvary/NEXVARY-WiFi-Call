#!/usr/bin/env bash
# Dedicated disposable hosted CI only. Never edits /etc or existing services.
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
cd "$(dirname "$0")/.."
command -v asterisk >/dev/null
command -v adb >/dev/null
python3 -c 'import pylibsrtp'
test -r /usr/share/asterisk/documentation/core-en_US.xml
# Refuse to collide with an existing TLS PBX listener.
if ss -H -ltn 'sport = :5061' | grep -q .; then
  echo 'Disposable SIP fixture port is occupied' >&2
  exit 1
fi
module_file=$(dpkg-query -L asterisk-modules | awk '/\/res_pjsip\.so$/ && !found { path=$0; found=1 } END { print path }')
test -r "$module_file"
runtime=$(mktemp -d)
pbx_pid=""
peer_pid=""
mkdir -p android-sip-evidence
asterisk -V > android-sip-evidence/asterisk-version.txt
grep -Eq '^Asterisk 20\.' android-sip-evidence/asterisk-version.txt || {
  echo 'Android SIP fixture requires the validated Asterisk 20 generation' >&2
  exit 1
}
cleanup() {
  status=$?
  trap - EXIT
  adb shell run-as com.nexvary.wificall rm -f files/nexvary-sip-e2e.json 2>/dev/null || true
  if [[ -n "$peer_pid" ]]; then kill "$peer_pid" 2>/dev/null || true; wait "$peer_pid" 2>/dev/null || true; fi
  if [[ -n "$pbx_pid" ]]; then kill "$pbx_pid" 2>/dev/null || true; wait "$pbx_pid" 2>/dev/null || true; fi
  if [[ "$status" -ne 0 ]]; then
    RUNTIME="$runtime" python3 - <<'PY'
import json, os
from pathlib import Path
r=Path(os.environ['RUNTIME'])
# Read a bounded private log and emit only fixed categories with counts.
# Never expose matched lines, addresses, identities, SDP or certificate details.
p=r/'pbx.log'
text=p.read_bytes()[:1024*1024].decode('utf-8', errors='replace').lower() if p.is_file() else ''
categories={
 'module_load_failure':('unable to load module', 'error loading module', 'could not load module'),
 'socket_bind_failure':('unable to bind', 'address already in use'),
 'tls_failure':('ssl error', 'ssl handshake', 'tls error', 'certificate verify'),
 'endpoint_identification_failure':('no matching endpoint',),
 'authentication_failure':('failed to authenticate', 'authentication failed'),
 'configuration_failure':('could not create an object', 'could not find option', 'invalid configuration'),
 'registrar_failure':('unable to register', 'no aor', 'could not find aor'),
 'dialplan_route_failure':('extension not found', 'not found in context', 'no such extension'),
 'contact_route_failure':('no contacts available', 'unable to create channel', 'could not create dialog', 'no route to destination'),
 'codec_negotiation_failure':('no joint capabilities', 'no compatible codecs', 'no matching codecs'),
 'media_negotiation_failure':('could not negotiate stream', 'no crypto', 'srtp unprotect failed', 'failed to initialize srtp'),
}
result={'synthetic':True,'success':False,'log_read_limit_bytes':1024*1024,
        'warning_categories':{name:sum(text.count(term) for term in terms) for name,terms in categories.items()}}
Path('android-sip-evidence/pbx-diagnostic-categories.json').write_text(json.dumps(result,indent=2)+'\n')
PY
  fi
  rm -rf "$runtime"
  exit "$status"
}
trap cleanup EXIT
# The emulator must see the host alias in Asterisk's own dialog Contact/Via,
# not host loopback. No local_net is configured: res_pjsip_nat must rewrite
# signalling for both fixture clients, including loopback-sourced QEMU traffic.
# The host peer sends on its existing verified TLS connection; only Android
# resolves the advertised alias. Listener remains private 127.0.0.1:5061.
python3 server/deploy/pbx/generate.py --output "$runtime/config" --external-address 10.0.2.2 >/dev/null
mkdir -p "$runtime/tls" "$runtime/run" "$runtime/log" "$runtime/spool" "$runtime/db"
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 1 \
  -subj '/CN=10.0.2.2' -addext 'subjectAltName=IP:10.0.2.2,IP:127.0.0.1' \
  -keyout "$runtime/tls/privkey.pem" -out "$runtime/tls/fullchain.pem" 2>/dev/null
chmod 600 "$runtime/tls/privkey.pem"
RUNTIME="$runtime" AST_MODULE_DIRECTORY="$(dirname "$module_file")" python3 - <<'PY'
import json, os
from pathlib import Path
r=Path(os.environ['RUNTIME'])
p=r/'config/pjsip.conf'
text=p.read_text().replace('/etc/asterisk/tls/', str(r/'tls')+'/').replace('direct_media=no', 'direct_media=no\nmedia_address=10.0.2.2')
text=text.replace('external_signaling_address=10.0.2.2', 'external_signaling_address=10.0.2.2\nexternal_signaling_port=5061')
assert 'bind=127.0.0.1:5061' in text and 'local_net=' not in text
p.write_text(text)
(r/'config/http.conf').write_text('[general]\nenabled=no\n')
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
account=json.loads((r/'config/accounts.json').read_text())['accounts']['1001']
fixture={'host':'10.0.2.2','port':5061,'username':'1001','password':account,'peer':'1002',
         'root_ca':(r/'tls/fullchain.pem').read_text(),'deadline_seconds':90}
(r/'android-fixture.json').write_text(json.dumps(fixture))
(r/'android-fixture.json').chmod(0o600)
PY
asterisk -f -C "$runtime/config/asterisk.conf" > "$runtime/pbx.log" 2>&1 &
pbx_pid=$!
ready=false
for attempt in $(seq 1 40); do
  if asterisk -C "$runtime/config/asterisk.conf" -rx 'pjsip show transports' 2>/dev/null | grep -q 'secure-tls'; then ready=true; break; fi
  kill -0 "$pbx_pid" 2>/dev/null || exit 1
  sleep 0.5
done
test "$ready" = true
# A TLS listener can appear before endpoint/auth/registrar initialization.
# Run the bounded native boot barrier, then independently require the generated
# accounts and both registration/authentication modules. CLI text stays private.
timeout 30 asterisk -C "$runtime/config/asterisk.conf" -rx 'core waitfullybooted' > "$runtime/boot-state.txt" 2>&1
ready=false
for attempt in $(seq 1 30); do
  asterisk -C "$runtime/config/asterisk.conf" -rx 'pjsip show endpoints' > "$runtime/endpoints.txt" 2>&1
  asterisk -C "$runtime/config/asterisk.conf" -rx 'pjsip show auths' > "$runtime/auths.txt" 2>&1
  asterisk -C "$runtime/config/asterisk.conf" -rx 'module show like res_pjsip_registrar.so' > "$runtime/registrar.txt" 2>&1
  asterisk -C "$runtime/config/asterisk.conf" -rx 'module show like res_pjsip_authenticator_digest.so' > "$runtime/authenticator.txt" 2>&1
  if grep -Eq 'Endpoint:[[:space:]]+1001([[:space:]]|/)' "$runtime/endpoints.txt" && \
     grep -Eq 'Endpoint:[[:space:]]+1002([[:space:]]|/)' "$runtime/endpoints.txt" && \
     grep -q 'auth-1001' "$runtime/auths.txt" && grep -q 'auth-1002' "$runtime/auths.txt" && \
     grep -q 'Running' "$runtime/registrar.txt" && grep -q 'Running' "$runtime/authenticator.txt"; then
    ready=true
    break
  fi
  kill -0 "$pbx_pid" 2>/dev/null || exit 1
  sleep 1
done
test "$ready" = true
printf '%s\n' '{"synthetic":true,"generated_endpoints_ready":2,"generated_auths_ready":2,"registrar_running":true,"digest_authenticator_running":true}' > android-sip-evidence/pbx-readiness.json
python3 scripts/pbx_android_peer.py --ca "$runtime/tls/fullchain.pem" --accounts "$runtime/config/accounts.json" \
  --ready "$runtime/peer-ready" --output android-sip-evidence/peer-result.json > "$runtime/peer.log" 2>&1 &
peer_pid=$!
for attempt in $(seq 1 40); do
  test ! -f "$runtime/peer-ready" || break
  kill -0 "$peer_pid" 2>/dev/null || exit 1
  sleep 0.5
done
test -f "$runtime/peer-ready"
adb shell run-as com.nexvary.wificall mkdir -p files
adb shell run-as com.nexvary.wificall sh -c '"cat > files/nexvary-sip-e2e.json"' < "$runtime/android-fixture.json"
adb shell rm -rf /sdcard/Download/NEXVARY-SIP-E2E
set +e
adb shell am instrument -w -e class com.nexvary.wificall.platform.sip.SipGatewayE2ETest \
  com.nexvary.wificall.test/androidx.test.runner.AndroidJUnitRunner > "$runtime/instrumentation.log" 2>&1
instrument_status=$?
set -e
adb pull /sdcard/Download/NEXVARY-SIP-E2E android-sip-evidence/android >/dev/null
# am instrument can return zero even after assertion failures. Require explicit
# runner success and machine-readable positive proofs, never expose raw logs.
test "$instrument_status" = 0
grep -q 'OK (1 test)' "$runtime/instrumentation.log"
wait "$peer_pid"
peer_pid=""
test -s android-sip-evidence/peer-result.json
python3 - <<'PY'
import json
from pathlib import Path
result=json.loads(Path('android-sip-evidence/android/result.json').read_text())
assert result['success'] is True, 'Android SIP E2E proof was not successful'
print('Android emulator SIP/TLS/SRTP synthetic integration passed')
PY

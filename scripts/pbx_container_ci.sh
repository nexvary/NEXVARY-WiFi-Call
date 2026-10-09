#!/usr/bin/env bash
# Disposable CI runner only. Uses a unique compose project and removes only its resources.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_ENVIRONMENT:-} == github-hosted ]] || { echo 'Hosted disposable CI required'; exit 2; }
runtime=$(mktemp -d)
project="nexvary-pbx-ci-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
compose=(docker compose -p "$project" --env-file "$runtime/compose.env" -f server/deploy/pbx/compose.yml)
cleanup() {
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  sudo rm -rf "$runtime"
}
trap cleanup EXIT
python3 server/deploy/pbx/generate.py --output "$runtime/config" --bind 0.0.0.0
mkdir "$runtime/tls"
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 1 \
  -subj '/CN=127.0.0.1' -addext 'subjectAltName=IP:127.0.0.1' \
  -keyout "$runtime/tls/privkey.pem" -out "$runtime/tls/fullchain.pem" 2>/dev/null
chmod 600 "$runtime/tls/privkey.pem"
sudo chown -R 10001:10001 "$runtime/config" "$runtime/tls"
cat > "$runtime/compose.env" <<ENV
NEXVARY_BIND_IP=127.0.0.1
NEXVARY_PBX_CONFIG=$runtime/config
NEXVARY_TLS_CERT=$runtime/tls/fullchain.pem
NEXVARY_TLS_KEY=$runtime/tls/privkey.pem
ENV
"${compose[@]}" build
"${compose[@]}" up -d
container=$("${compose[@]}" ps -q pbx)
for attempt in $(seq 1 60); do
  status=$(docker inspect --format '{{.State.Health.Status}}' "$container")
  [[ $status != healthy ]] || break
  [[ $status != unhealthy ]] || { echo 'PBX container unhealthy'; exit 1; }
  sleep 1
done
[[ $status == healthy ]] || { echo 'Container readiness deadline exceeded'; exit 1; }
mkdir -p pbx-container-evidence
docker inspect --format '{{json .HostConfig}}' "$container" | python3 -c '
import json,sys
c=json.load(sys.stdin)
assert c["ReadonlyRootfs"] and not c["Privileged"] and c["NetworkMode"] != "host"
assert "ALL" in c["CapDrop"] and not c["Devices"]
assert set(c["PortBindings"]) == {"5061/tcp"} | {str(p)+"/udp" for p in range(20000,20101)}
assert all(b["HostIp"] == "127.0.0.1" for v in c["PortBindings"].values() for b in v)
print(json.dumps({"synthetic":True,"container_startup":True,"read_only_root":True,"nonprivileged":True,"host_network":False,"public_admin_listener":False,"user_server_tested":False}))
' > pbx-container-evidence/isolation.json
[[ $(docker inspect --format '{{.Config.User}}' "$container") == '10001:10001' ]]
"${compose[@]}" exec -T pbx asterisk -V > pbx-container-evidence/version.txt

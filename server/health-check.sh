#!/usr/bin/env bash
# Runtime inventory only. Container running is not evidence of a working carrier call.
set -uo pipefail
export LC_ALL=C
[[ $# == 0 ]] || { printf 'Usage: bash server/health-check.sh\n' >&2; exit 2; }
printf 'NEXVARY host checks at %s\n' "$(date -u +%FT%TZ)"
run() {
  command -v "$1" >/dev/null 2>&1 || { printf 'UNAVAILABLE: %s\n' "$1"; return; }
  local rc=0
  if command -v timeout >/dev/null 2>&1; then timeout 10s "$@" 2>&1 || rc=$?; else "$@" 2>&1 || rc=$?; fi
  ((rc == 0)) || printf 'CHECK INCOMPLETE: exit %d\n' "$rc"
  return 0
}
run free -h
run df -h /
run systemctl is-active vowifi-control.service
run systemctl is-active pcscd.service
run systemctl is-active docker.service
run docker ps --filter 'name=vowifi' --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
run ss -lntu
printf '\nCarrier evidence: NOT TESTED by this script.\n'
printf 'Independently record SIM detection, ePDG DNS, SWu authentication, IMS registration,\n'
printf 'outbound call, inbound call and bidirectional audio with time/device/carrier scope.\n'
printf 'Do not share raw logs, SIM identifiers or AKA/session-key material.\n'

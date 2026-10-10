#!/usr/bin/env bash
# Read-only host inventory. Does not install packages, change firewall, or contact a SIM.
set -uo pipefail
export LC_ALL=C
usage() { printf 'Usage: bash server/preflight.sh [--epdg HOSTNAME] [--public-ip]\n'; }
epdg=''
public_ip=false
while (($#)); do
  case "$1" in
    --epdg) [[ $# -ge 2 ]] || { usage; exit 2; }; epdg=$2; shift 2 ;;
    --public-ip) public_ip=true; shift ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
if [[ -n $epdg ]] && { [[ ${#epdg} -gt 253 ]] || [[ ! $epdg =~ ^[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$ ]] || [[ $epdg == *..* ]]; }; then
  printf 'Invalid hostname; pass a DNS name, not an address, URL, or SIM identifier.\n' >&2; exit 2
fi
section() { printf '\n[%s]\n' "$1"; }
run() {
  if ! command -v "$1" >/dev/null 2>&1; then printf 'UNAVAILABLE: %s\n' "$1"; return; fi
  local rc=0
  if command -v timeout >/dev/null 2>&1; then timeout 12s "$@" 2>&1 || rc=$?; else "$@" 2>&1 || rc=$?; fi
  if ((rc)); then printf 'CHECK INCOMPLETE: exit %d (permissions or service availability may limit this result)\n' "$rc"; fi
}
printf 'NEXVARY gateway preflight: read-only, UTC %s\n' "$(date -u +%FT%TZ)"
printf 'Contains host addresses and service names. Review/redact before sharing.\n'
section OS
[[ ! -r /etc/os-release ]] || cat /etc/os-release
run uname -srmo
run id
section CPU
run getconf _NPROCESSORS_ONLN
run lscpu
section 'RAM and swap'
run free -h
run swapon --show --bytes
if [[ -r /proc/meminfo ]]; then
  ram_kib=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
  swap_kib=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
  if ((ram_kib < 2097152 && swap_kib < 2097152)); then
    printf 'ACTION: below 2 GiB RAM and swap. Review a 2–4 GiB swap plan before builds; none created.\n'
  fi
fi
section Disk
run df -hT / /var /tmp
run df -i / /var /tmp
section 'Docker (read-only; no container environment/secrets)'
run docker --version
run docker compose version
run docker info --format 'Server={{.ServerVersion}} Storage={{.Driver}} CPUs={{.NCPU}} RAM={{.MemTotal}}'
run docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
section 'Listening ports'
run ss -lntu
section Firewall
run ufw status verbose
run nft list tables
# Rules may embed sensitive IPs; inventory only, no flush or policy changes.
run iptables -S
section 'Existing services and systemd'
run systemctl is-system-running
run systemctl --no-pager --plain list-units --type=service --state=running
run systemctl --no-pager --plain list-unit-files vowifi-control.service pcscd.service docker.service
section 'IPv4 and IPv6'
run ip -brief -4 address show
run ip -brief -6 address show
run ip -4 route show
run ip -6 route show
section DNS
run resolvectl status
if [[ -r /etc/resolv.conf ]]; then awk '/^(nameserver|search|options)/' /etc/resolv.conf; fi
if [[ -n $epdg ]]; then run getent ahosts "$epdg"; fi
if $public_ip; then
  printf 'Optional outbound DNS query to OpenDNS (observed public IPv4; not a binding guarantee):\n'
  run dig +time=3 +tries=1 +short myip.opendns.com @resolver1.opendns.com
fi
section 'Kernel tunnel support'
[[ ! -e /dev/net/tun ]] || run ls -l /dev/net/tun
if [[ ! -e /dev/net/tun ]]; then printf 'NOT PRESENT: /dev/net/tun\n'; fi
run ip xfrm state count
section 'Decision'
printf 'Inventory only. No ePDG, IPsec, IMS, call or audio success has been established.\n'
printf 'Missing tools/permission-limited checks must be resolved on the actual host before deployment.\n'

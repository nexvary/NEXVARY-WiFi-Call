#!/usr/bin/env bash
# Prepare pinned upstream sources for audit. Never runs the upstream installer.
set -euo pipefail
revision=e3719840b93961f933aab3dac8bd2641936e2bcc
repo=https://github.com/pagecat/vowifi_gateway.git
base_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
state_dir="$base_dir/work"
usage() { printf 'Usage: bash server/install.sh [--plan | --prepare-source]\n'; }
case "${1:---plan}" in
  --help) usage; exit 0 ;;
  --plan)
    cat <<PLAN
No host changes will be made.
1. Run: bash server/preflight.sh (on the actual Ubuntu server).
2. Test Phone-as-SIM privileges on the actual phone/SIM first.
3. Prepare pinned sources: bash server/install.sh --prepare-source
   Upstream: $repo at $revision
4. Review server/docs/GATEWAY-POC.md gates: fail-closed AKA, no Ki path,
   no persisted session keys, authenticated phone adapter, dependency licenses.
5. Build the engine off-server; transfer a reviewed immutable image.
6. Deploy one SIM, native localhost-only control plane; preserve existing services.
No packages, swap, firewall, systemd services, or containers are changed here.
PLAN
    ;;
  --prepare-source)
    [[ $# == 1 ]] || { usage >&2; exit 2; }
    command -v git >/dev/null || { printf 'git required; install separately.\n' >&2; exit 1; }
    [[ ! -e "$state_dir" ]] || { printf 'Refusing to overwrite existing %s\n' "$state_dir" >&2; exit 1; }
    mkdir -m 700 "$state_dir"
    printf '%s\n' "$revision" > "$state_dir/.nexvary-prepared-source"
    git -C "$state_dir" init --quiet upstream
    git -C "$state_dir/upstream" remote add origin "$repo"
    git -C "$state_dir/upstream" fetch --depth 1 origin "$revision"
    git -C "$state_dir/upstream" checkout --detach --quiet FETCH_HEAD
    [[ $(git -C "$state_dir/upstream" rev-parse HEAD) == "$revision" ]]
    printf 'Prepared sources at %s; no gateway installed or started.\n' "$state_dir/upstream"
    ;;
  *) usage >&2; exit 2 ;;
esac

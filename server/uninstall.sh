#!/usr/bin/env bash
# Reverses only source preparation by archiving it. Never deletes runtime data or changes services.
set -euo pipefail
base_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
state_dir="$base_dir/work"
revision=e3719840b93961f933aab3dac8bd2641936e2bcc
case "${1:---plan}" in
  --plan|--help)
    printf 'No gateway deployment is owned by these preparation scripts.\n'
    printf 'Use --archive-source to move only marked prepared sources to a dated backup.\n'
    printf 'Existing services, images, volumes, packages, swap and firewall are preserved.\n'
    ;;
  --archive-source)
    [[ $# == 1 ]] || exit 2
    [[ -d "$state_dir" && ! -L "$state_dir" && -f "$state_dir/.nexvary-prepared-source" ]] || { printf 'No owned prepared sources; refusing.\n' >&2; exit 1; }
    [[ $(cat "$state_dir/.nexvary-prepared-source") == "$revision" ]] || { printf 'Ownership revision mismatch; refusing.\n' >&2; exit 1; }
    backup="$base_dir/work.archived.$(date -u +%Y%m%dT%H%M%SZ)"
    [[ ! -e "$backup" ]] || { printf 'Backup already exists; refusing.\n' >&2; exit 1; }
    mv -- "$state_dir" "$backup"
    printf 'Archived prepared sources at %s. No data deleted.\n' "$backup"
    ;;
  *) printf 'Usage: bash server/uninstall.sh [--plan | --archive-source]\n' >&2; exit 2 ;;
esac

#!/usr/bin/env python3
"""Bounded, read-only inventory. No probing endpoints, packages, secrets or mutations."""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

CHECKS = {
    'os': ['uname', '-srmo'],
    'cpu': ['getconf', '_NPROCESSORS_ONLN'],
    'memory': ['free', '-b'],
    'swap': ['swapon', '--show', '--bytes'],
    'disk': ['df', '-B1', '/', '/var', '/tmp'],
    'services': ['systemctl', '--no-pager', '--plain', 'list-units', '--type=service', '--state=running'],
    'listeners': ['ss', '-H', '-lntu'],
    'docker_version': ['docker', '--version'],
    'docker_compose': ['docker', 'compose', 'version'],
    'containers': ['docker', 'ps', '--format', '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'],
    'ufw': ['ufw', 'status', 'verbose'],
    'nft_tables': ['nft', 'list', 'tables'],
    'firewall_rules': ['iptables', '-S'],
    'interfaces': ['ip', '-brief', 'address', 'show'],
    'routes_v4': ['ip', '-4', 'route', 'show'],
    'routes_v6': ['ip', '-6', 'route', 'show'],
    'dns': ['resolvectl', 'status'],
    'isolation': ['unshare', '--version'],
    'systemd': ['systemd', '--version'],
    'cgroups': ['stat', '-fc', '%T', '/sys/fs/cgroup'],
}

def run(argv):
    if not shutil.which(argv[0]):
        return {'status': 'missing_tool', 'output': ''}
    try:
        # No shell, inherited proxy/credential env, or sudo invocation.
        p = subprocess.run(argv, capture_output=True, text=True, timeout=12,
                           env={'PATH': os.defpath + ':/usr/sbin:/sbin', 'LC_ALL': 'C'})
        return {'status': 'ok' if p.returncode == 0 else 'incomplete',
                'exit_code': p.returncode, 'output': p.stdout[:65536],
                'error': p.stderr[:4096]}
    except (OSError, subprocess.TimeoutExpired):
        return {'status': 'incomplete', 'output': '', 'error': 'command unavailable or deadline exceeded'}


def listening_ports(output):
    ports = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 5:
            match = re.search(r':([0-9]+)$', parts[4])
            if match:
                ports.add(int(match.group(1)))
    return sorted(ports)


def deploy_plan(checks):
    ports = listening_ports(checks.get('listeners', {}).get('output', ''))
    blockers = []
    for name in ('services', 'listeners', 'memory', 'disk', 'interfaces', 'routes_v4'):
        if checks.get(name, {}).get('status') != 'ok':
            blockers.append('incomplete_' + name)
    # Both nft and iptables may exist; none of these inventory outputs establishes
    # end-to-end reachability or authorizes opening a port.
    if checks.get('ufw', {}).get('status') != 'ok' and checks.get('firewall_rules', {}).get('status') != 'ok':
        blockers.append('firewall_review_required')
    conflicts = sorted(set(ports) & {5060, 5061, 8088, 8089, 8787})
    rtp_conflicts = [p for p in ports if 20000 <= p <= 20100]
    if conflicts or rtp_conflicts:
        blockers.append('candidate_port_conflict')
    mem = checks.get('memory', {}).get('output', '')
    m = re.search(r'^Mem:\s+(\d+)\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+)', mem, re.M)
    if not m:
        blockers.append('resource_review_required')
    elif int(m.group(2)) < 512 * 1024**2:
        blockers.append('low_available_memory')
    disk_rows = checks.get('disk', {}).get('output', '').splitlines()[1:]
    for row in disk_rows:
        fields = row.split()
        if len(fields) >= 6 and fields[3].isdigit() and int(fields[3]) < 2 * 1024**3:
            blockers.append('low_disk_space')
    release = checks.get('os_release', {}).get('output', '')
    if not re.search(r'^ID=ubuntu$', release, re.M) or not re.search(r'^VERSION_ID="24\.04"$', release, re.M):
        blockers.append('os_compatibility_review_required')
    services = checks.get('services', {}).get('output', '')
    containers = checks.get('containers', {}).get('output', '')
    protected = [line for line in (services + '\n' + containers).splitlines()
                 if re.search(r'outline|shadowbox|shadowsocks|nexvary|fg.?mtm|nginx|apache', line, re.I)]
    return {
        'state': 'needs_review', 'automatic_deployment_allowed': False,
        'blockers': sorted(set(blockers)), 'candidate_conflicting_ports': conflicts,
        'candidate_rtp_conflicts': rtp_conflicts,
        'protected_service_inventory': protected,
        'voice_gateway_location': 'physical_host_with_cellular_coverage',
        'recommended_split': 'existing_control_server_and_separate_voice_gateway',
        'tls': 'certificate_identity_and_trust_require_separate_review',
        'network': 'TLS signaling and SRTP media need explicit reachability/NAT review; listener inventory is not proof',
        'resources': 'single-call pilot budget: 1 core, 512 MiB available RAM, 2 GiB free disk; load testing required',
        'isolation': 'unshare availability is not proof of namespace permission; no namespace created by this tool',
        'next_step': 'review actual report before generating local PBX config; do not stop services or alter firewall',
    }


def inspect():
    checks = {name: run(argv) for name, argv in CHECKS.items()}
    # OS release is public metadata. Never read web/proxy configs or private keys.
    try:
        checks['os_release'] = {'status': 'ok', 'output': Path('/etc/os-release').read_text()[:4096]}
    except OSError:
        checks['os_release'] = {'status': 'incomplete', 'output': ''}
    checks['web_services'] = run(['systemctl', 'is-active', 'nginx.service', 'apache2.service'])
    checks['tls_tool'] = run(['openssl', 'version'])
    return {'schema': 'nexvary.preflight.v1', 'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'read_only': True, 'contains_host_addresses': True,
            'checks': checks, 'plan': deploy_plan(checks)}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(inspect(), indent=2, ensure_ascii=False))

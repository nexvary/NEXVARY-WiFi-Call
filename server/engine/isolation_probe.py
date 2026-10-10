"""Opt-in namespace isolation probe; never starts the gateway or authenticates a SIM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile


def command(args, timeout=10):
    result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    if result.returncode or len(result.stdout) > 262144:
        raise RuntimeError('Required isolation check unavailable.')
    return result.stdout


def stable(value):
    # Kernel expiry/counter fields change with time independently of this probe.
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items()
                if k not in {'expires', 'used', 'lastuse', 'cache', 'stats64', 'stats'}}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def inventory():
    state = {}
    for family in ('-4', '-6'):
        for name, args in (('routes', ['route', 'show', 'table', 'all']), ('rules', ['rule', 'show'])):
            state[family + name] = stable(json.loads(command(['ip', '-j', family, *args])))
    state['dns'] = hashlib.sha256(Path('/etc/resolv.conf').read_bytes()).hexdigest()
    state['namespaces'] = {name: os.readlink('/proc/self/ns/' + name) for name in ('net', 'mnt', 'pid')}
    return state


def child(expected, resolver, proof_socket=None):
    # Check isolation before executing even the private mount operation.
    before = inventory()
    if not all(before['namespaces'][name] != expected[name] for name in expected):
        raise RuntimeError('Namespace isolation not established.')
    if os.getpid() != 1 or before['-4routes'] or before['-6routes']:
        raise RuntimeError('Fresh network/PID namespaces required.')
    if {x['ifname'] for x in json.loads(command(['ip', '-j', 'link', 'show']))} != {'lo'}:
        raise RuntimeError('Unexpected interface in isolated namespace.')
    # unshare makes mount propagation private before this bind. The destination
    # is intentionally the resolver path; its backing host file is never written.
    command(['mount', '--bind', resolver, '/etc/resolv.conf'])
    marker = b'# NEXVARY isolated probe only\nnameserver 127.0.0.1\n'
    Path('/etc/resolv.conf').write_bytes(marker)
    if Path(resolver).read_bytes() != marker:
        raise RuntimeError('Private resolver mount not established.')
    try:
        with socket.create_connection(('127.0.0.1', 8787), timeout=1):
            raise RuntimeError('Unexpected host loopback access.')
    except (ConnectionRefusedError, TimeoutError, OSError):
        pass
    if proof_socket is not None:
        # CI-only synthetic sentinel, never an AKA request or credential.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(3)
            channel.connect(proof_socket)
            channel.sendall(b'NEXVARY-ISOLATION-PROBE\n')
            if channel.recv(64) != b'private-unix-bridge-alive':
                raise RuntimeError('Private Unix transport unavailable.')
    return {'network_isolated': True, 'mount_isolated': True, 'pid_isolated': True,
            'dns_write_private': True, 'host_loopback_unreachable': True}


def probe(proof_socket=None):
    if os.geteuid() != 0:
        raise RuntimeError('The explicit probe requires sudo on the actual host.')
    for tool in ('unshare', 'mount', 'ip'):
        if shutil.which(tool) is None:
            raise RuntimeError('Required namespace tool unavailable.')
    before = inventory()
    with tempfile.TemporaryDirectory(prefix='nexvary-isolation-') as directory:
        resolver = Path(directory) / 'resolv.conf'
        resolver.write_bytes(Path('/etc/resolv.conf').read_bytes())
        os.chmod(resolver, 0o600)
        args = ['unshare', '--net', '--mount', '--pid', '--fork', '--kill-child=SIGKILL', '--mount-proc',
                '--propagation', 'private', sys.executable, str(Path(__file__).resolve()),
                '--child', json.dumps(before['namespaces']), str(resolver)]
        if proof_socket is not None:
            args.extend(['--unix-proof', proof_socket])
        try:
            result = json.loads(command(args, timeout=20))
        finally:
            after = inventory()
            if before != after:
                raise RuntimeError('Host routes, rules, resolver or namespace changed; review actual host state.')
    expected = {'network_isolated', 'mount_isolated', 'pid_isolated',
                'dns_write_private', 'host_loopback_unreachable'}
    if not isinstance(result, dict) or set(result) != expected or not all(v is True for v in result.values()):
        raise RuntimeError('Incomplete namespace verification.')
    return {**result, 'host_state_unchanged': True, 'gateway_started': False,
            'carrier_authentication_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--child', nargs=2, help=argparse.SUPPRESS)
    parser.add_argument('--unix-proof', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.child:
            if args.probe:
                raise RuntimeError('Invalid isolation mode.')
            result = child(json.loads(args.child[0]), args.child[1], args.unix_proof)
        elif args.probe:
            if args.unix_proof:
                raise RuntimeError('Synthetic Unix proof is internal to CI only.')
            result = probe()
        else:
            if args.unix_proof:
                raise RuntimeError('Invalid isolation mode.')
            result = {'plan_only': True, 'gateway_started': False,
                      'next_command': 'sudo python3 server/engine/isolation_probe.py --probe'}
        print(json.dumps(result, sort_keys=True))
    except Exception:
        # Do not print host addresses, namespace contents, credentials or errors.
        parser.exit(1, 'Isolation probe refused or failed; no gateway was started. Review tools, privileges and host state.\n')


if __name__ == '__main__':
    main()

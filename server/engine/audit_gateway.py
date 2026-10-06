"""Read-only pinned-source audit. A verified inventory never unlocks execution."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import stat
import subprocess

PIN = 'e3719840b93961f933aab3dac8bd2641936e2bcc'
HASHES = {
    'engine/swu_ike.py': '74e62791409e01a07bb435b0c0ec1b87ab3a2a486d547803fbc7862f3d2e920e',
    'engine/ami_usim.py': 'eb334f022006b00374f4480e6de48a5b5463b4c1a00e0ae10e0496486125a509',
    'LICENSE': '08ed6eceeaf1206534732402c436928ee337c740d22cc8bf8903c26306364fc3',
    'engine/entrypoint.sh': '34323deca452b603411e72019b197c1da5b148ad3f572d76fb80a379860a715a',
    'engine/Dockerfile': '961105e748c47ca2af856f05755ef2bb97a03fbf8e93c58da3ffd1a713a79365',
    'engine/render.py': '5f3aa54dafbc700d398100457b4e4e4ccbb98328ffd7c5bd0d30fb4e35dd3feb',
    'control/app/engine.py': '963d4b838d7fd91a6ee14cc372d18672b2815783f528e97b75ff3b5270e0b1fe',
}
BLOCKERS = [
    'Original source contains fabricated identity/authentication fallbacks, software Ki paths and sensitive diagnostics; use only the separately hardened audit stage.',
    'SWu routes, policy table 51820 and priority 100, TUN creation and cleanup require validated namespace ownership and checked argument-list subprocesses.',
    'DNS cleanup can restore a backup even when this run did not enable DNS rewriting; filesystem isolation and verified ownership are required.',
    'Upstream --netns isolates the inner TUN/routes, not the whole engine process; require full network and mount isolation.',
    'Original entrypoint starts physical-reader/PIN helpers and enables Asterisk SIP logging; do not execute it for the phone bridge.',
    'Control plane uses privileged Docker/socket access and publishes SIP/AMI/WSS/RTP ports; no host control-plane deployment is approved.',
    'Dependency revisions, licenses and Asterisk IMS security mutations remain unreviewed; root repository MIT does not license every dependency.',
    'Real authorized subscriber/carrier identity and a live public-API phone authentication result remain prerequisites; sanitized reports contain no IMSI.',
    'Namespace connectivity and private Unix AKA transport must be verified; a namespace has separate loopback.',
    'No resource, ePDG, IPsec, IMS, call or audio result is established by static source inspection; retain the staged execution gate.',
]


class AuditRefused(ValueError):
    pass


def _git(source, *args):
    return subprocess.check_output(['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-C', str(source), *args],
                                   stderr=subprocess.DEVNULL, timeout=10)


def _name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _name(node.value) + '.' + node.attr
    return ''


def inventory(source):
    """Analyze syntax only; export locations and categories, never call arguments."""
    tree = ast.parse(source)
    imported = set()
    findings = []
    class Visitor(ast.NodeVisitor):
        scope = []
        def visit_ClassDef(self, node):
            self.scope.append(node.name); self.generic_visit(node); self.scope.pop()
        def visit_FunctionDef(self, node):
            self.scope.append(node.name); self.generic_visit(node); self.scope.pop()
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_Import(self, node):
            imported.update(item.name.split('.')[0] for item in node.names)
        def visit_ImportFrom(self, node):
            if node.module:
                imported.add(node.module.split('.')[0])
        def visit_Call(self, node):
            name = _name(node.func)
            category = None
            if name.startswith('subprocess.') or name in {'os.system', 'os.execv', 'os.execve'}:
                category = 'subprocess_execution'
            elif name == 'socket.socket': category = 'network_socket'
            elif name == 'fcntl.ioctl': category = 'device_control'
            elif name in {'os.open', 'os.write'}: category = 'raw_descriptor_access'
            elif name in {'os.makedirs', 'os.mkdir', 'os.replace', 'os.remove', 'os.unlink'}: category = 'filesystem_mutation'
            elif isinstance(node.func, ast.Attribute) and node.func.attr in {'write_text', 'write_bytes'}:
                category = 'potential_path_write_method'
            elif isinstance(node.func, ast.Attribute) and node.func.attr == 'write':
                category = 'potential_stream_write_method'
            elif name == 'open':
                mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == 'mode'), None)
                if mode is not None and (not isinstance(mode, ast.Constant) or not isinstance(mode.value, str) or any(c in mode.value for c in 'wa+')):
                    category = 'file_write_or_dynamic_mode'
            if category:
                findings.append(dict(function='.'.join(self.scope) or '<module>', line=node.lineno,
                                     category=category, call=name,
                                     shell=any(k.arg == 'shell' and not (isinstance(k.value, ast.Constant) and k.value.value is False) for k in node.keywords)))
            self.generic_visit(node)
    Visitor().visit(tree)
    return dict(import_roots=sorted(imported), mutation_sites=findings,
                completeness='Static syntax inventory only; indirect/aliased calls and imported code require separate review.')


def audit(source):
    try:
        source = Path(source).absolute()
        if any(path.is_symlink() for path in (source, *source.parents)) or not source.is_dir():
            raise AuditRefused()
        metadata = source / '.git'
        if metadata.is_symlink() or not metadata.is_dir():
            raise AuditRefused()
        if _git(source, 'rev-parse', 'HEAD').decode().strip() != PIN:
            raise AuditRefused()
        if _git(source, 'status', '--porcelain', '--untracked-files=all').strip():
            raise AuditRefused()
        contents = {}
        for relative, expected in HASHES.items():
            path = source / relative
            if any(part.is_symlink() for part in (path, *path.parents)) or not stat.S_ISREG(path.stat().st_mode):
                raise AuditRefused()
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise AuditRefused()
            contents[relative] = data.decode('utf-8')
        swu = inventory(contents['engine/swu_ike.py'])
        functions = {item['function'] for item in swu['mutation_sites']}
        if not {'swu.set_routes', 'swu.delete_routes', 'swu.open_tun', 'swu.exec_in_netns', 'swu.create_socket_esp'} <= functions:
            raise AuditRefused()
        return dict(schema_version=1, upstream_revision=PIN, integrity_verified=True,
                    executable=False, gateway_verified=False, license='MIT (pinned upstream root notice only)',
                    source_sha256=HASHES.copy(), swu=swu,
                    supporting_source_inventory={name: inventory(contents[name]) for name in ('engine/ami_usim.py', 'engine/render.py', 'control/app/engine.py')},
                    blockers=BLOCKERS.copy(),
                    minimal_swu_only_candidate=dict(
                        distributions=['cryptography', 'pycryptodome'],
                        status='Candidate after legacy helper/import removal and per-component license/hash review; not an install manifest.',
                        legacy_import_roots=['serial', 'requests', 'smartcard', 'CryptoMobile', 'card'],
                        standard_library='Keep actual stdlib imports reported above; include the stdlib Phone-as-SIM adapter.',
                        excluded_for_first_probe=['Asterisk', 'pjproject', 'PCSC reader/PIN keeper', 'privileged upstream control plane'],
                        host_tools=['iproute2 (argv-only mutation helper still requires review)', 'legacy net-tools route/ifconfig calls must be replaced'],
                        resource_verification=False))
    except Exception:
        raise AuditRefused('Pinned read-only audit refused; source integrity or expected structure was not verified.') from None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    try:
        result = audit(args.source)
    except AuditRefused:
        print(json.dumps(dict(schema_version=1, integrity_verified=False, executable=False, gateway_verified=False,
                              error='Source audit refused.')))
        raise SystemExit(1)
    print(json.dumps(result, sort_keys=True, indent=2))
    raise SystemExit(2)  # Inventory is valid, but executable approval is deliberately withheld.

"""Stage an exact upstream snapshot for audit. Never install or execute upstream.

The staged entry points remain deliberately disabled. This is a narrow privacy
patch, not a security review of networking, subprocesses or the full gateway.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

PIN = 'e3719840b93961f933aab3dac8bd2641936e2bcc'
HASHES = {
    'engine/swu_ike.py': '74e62791409e01a07bb435b0c0ec1b87ab3a2a486d547803fbc7862f3d2e920e',
    'engine/ami_usim.py': 'eb334f022006b00374f4480e6de48a5b5463b4c1a00e0ae10e0496486125a509',
}
DISABLED = {'swu_log', 'swu_write_status', 'write_status',
            'print_ikev2_decryption_table', 'print_esp_sa'}
LEGACY = {'milenage_res_ck_ik', 'return_auts', 'get_imsi', 'get_res_ck_ik',
          'read_imsi', 'read_res_ck_ik_2', 'read_imsi_2', 'https_imsi',
          'https_res_ck_ik', '_read_res_ck_ik_pin'}
WRAPPERS = '''
def return_imsi(serial_interface_or_reader_index):
    from nexvary_aka_backend import get_backend
    try:
        value = get_backend().identity()
    except Exception:
        raise RuntimeError('Identity unavailable') from None
    if not isinstance(value, str) or not value.isascii() or not value.isdigit() or not 5 <= len(value) <= 15:
        raise RuntimeError('Identity unavailable')
    return value

def _nexvary_vector(value, ami=False):
    if not isinstance(value, tuple) or len(value) != (4 if ami else 3):
        raise RuntimeError('Authentication unavailable')
    def valid(item, low, high):
        return isinstance(item, str) and low <= len(item) <= high and len(item) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in item)
    res, ck, ik = value[:3]
    auts = value[3] if ami else res
    if (ami and res is None) or (not ami and ck is None and ik is None):
        if ik is not None or ck is not None or not valid(auts, 28, 28):
            raise RuntimeError('Authentication unavailable')
    elif not valid(res, 8, 32) or not valid(ck, 32, 32) or not valid(ik, 32, 32) or (ami and auts is not None):
        raise RuntimeError('Authentication unavailable')
    return value

def return_res_ck_ik(serial_interface_or_reader_index, rand, autn, ki=None, op=None, opc=None):
    if any(x is not None for x in (ki, op, opc)):
        raise RuntimeError('Long-term credentials prohibited')
    from nexvary_aka_backend import get_backend
    try:
        value = get_backend().authenticate(rand, autn)
    except Exception:
        raise RuntimeError('Authentication unavailable') from None
    return _nexvary_vector(value)

def read_res_ck_ik(reader_spec, rand, autn):
    from nexvary_aka_backend import get_backend
    try:
        value = get_backend().authenticate_ami(rand, autn)
    except Exception:
        raise RuntimeError('Authentication unavailable') from None
    return _nexvary_vector(value, ami=True)
'''


def _raise(message):
    return ast.parse('raise RuntimeError(' + repr(message) + ')').body[0]


class Hardener(ast.NodeTransformer):
    def __init__(self, ami):
        self.ami = ami

    def visit_ImportFrom(self, node):
        if node.module and 'Milenage' in node.module:
            return None
        return node

    def visit_FunctionDef(self, node):
        if node.name in DISABLED:
            node.body = [ast.Pass()]
            return node
        if node.name in LEGACY or (node.name == 'read_res_ck_ik' and not self.ami):
            node.body = [_raise('Legacy authentication disabled')]
            return node
        if node.name in {'return_imsi', 'return_res_ck_ik'} or (self.ami and node.name == 'read_res_ck_ik'):
            return None
        node = self.generic_visit(node)
        if node.name == '__init__' and any(a.arg == 'ki' for a in node.args.args):
            node.body.insert(0, ast.parse("if any(x is not None for x in (ki, op, opc, sqn)): raise RuntimeError('Long-term credentials prohibited')").body[0])
        return node

    def visit_If(self, node):
        # Remove the entire monkeypatch, not only its print statements.
        if any(isinstance(n, ast.Constant) and n.value == 'SWU_APDU_DEBUG' for n in ast.walk(node.test)):
            return None
        if any(isinstance(n, ast.Attribute) and n.attr == 'sqn' for n in ast.walk(node.test)):
            return [self.visit(n) for n in node.orelse] or ast.Pass()
        if isinstance(node.test, ast.Compare) and any(isinstance(n, ast.Name) and n.id == '__name__' for n in ast.walk(node.test)):
            node.body = [_raise('Audit staging only: upstream execution has not been reviewed')]
            node.orelse = []
            return node
        return self.generic_visit(node)

    def visit_Assign(self, node):
        if any(isinstance(t, ast.Name) and t.id in {'DEFAULT_IMSI', 'DEFAULT_RES', 'DEFAULT_CK', 'DEFAULT_IK', 'DEFAULT_MCC', 'DEFAULT_MNC'} for t in node.targets):
            node.value = ast.Constant(None)
        return self.generic_visit(node)

    def visit_Attribute(self, node):
        if isinstance(node.ctx, ast.Load) and isinstance(node.value, ast.Name) and node.value.id == 'options' and node.attr in {'ki', 'op', 'opc', 'sqn'}:
            return ast.Constant(None)
        return node

    def visit_Call(self, node):
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
        if name == 'print' or name in DISABLED or name in {'debug', 'info', 'warning', 'error', 'exception', 'critical', 'log'}:
            return ast.Constant(None)  # Do not evaluate potentially secret diagnostic arguments.
        if name == 'add_option' and any(isinstance(n, ast.Constant) and n.value in {'--ki', '--op', '--opc', '--sqn'} for n in node.args):
            return ast.Constant(None)
        return self.generic_visit(node)

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'send_action':
            for arg in node.value.args:
                if isinstance(arg, ast.Dict):
                    pairs = {k.value: v.value for k, v in zip(arg.keys, arg.values) if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}
                    keys = {k.value for k in arg.keys if isinstance(k, ast.Constant)}
                    if pairs.get('Action') == 'AuthResponse' and not keys.intersection({'RES', 'AUTS'}):
                        return _raise('Authentication unavailable')
        return self.generic_visit(node)


def patch_source(source, ami=False):
    tree = Hardener(ami).visit(ast.parse(source))
    wrappers = ast.parse(WRAPPERS).body
    allowed = {'_nexvary_vector', 'read_res_ck_ik'} if ami else {'_nexvary_vector', 'return_imsi', 'return_res_ck_ik'}
    tree.body[0:0] = [n for n in wrappers if n.name in allowed]
    tree.body.insert(0, ast.parse("if __name__ == '__main__': raise RuntimeError('Audit staging only: upstream execution has not been reviewed')").body[0])
    ast.fix_missing_locations(tree)
    output = '# Modified by NEXVARY: privacy audit staging only. Upstream MIT license retained in LICENSE.\n' + ast.unparse(tree) + '\n'
    compile(output, '<staged-audit>', 'exec')  # Syntax only, never execute.
    return output


def _git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.DEVNULL)


def stage(source, destination):
    source = Path(source).resolve(strict=True)
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Destination must be fresh')
    parent = destination.parent.resolve(strict=True)
    if parent == source or source in parent.parents:
        raise ValueError('Destination must be outside upstream')
    destination = parent / destination.name
    if _git(source, 'rev-parse', 'HEAD').decode().strip() != PIN:
        raise ValueError('Wrong upstream revision')
    if _git(source, 'status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('Upstream must be clean')
    files = _git(source, 'ls-files', '-z').decode().split('\0')
    for rel in filter(None, files):
        path = source / rel
        if path.is_symlink() or not path.is_file() or source not in path.resolve().parents:
            raise ValueError('Only regular tracked files supported')
    for rel, expected in HASHES.items():
        if hashlib.sha256((source / rel).read_bytes()).hexdigest() != expected:
            raise ValueError('Pinned source hash mismatch')
    adapter = Path(__file__).resolve().with_name('nexvary_aka_backend.py')
    if adapter.is_symlink() or not adapter.is_file():
        raise ValueError('Reviewed backend adapter missing')
    adapter_bytes = adapter.read_bytes()
    compile(adapter_bytes, '<backend-adapter>', 'exec')
    os.mkdir(destination, 0o700)
    # A partial stage remains visibly marked on failure; never overwrite it.
    (destination / '.nexvary-audit-stage').write_text('audit-only\n')
    for rel in filter(None, files):
        out = destination / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, out)
        out.chmod(0o600)  # Nothing in this audit copy is an executable installer.
    for rel in HASHES:
        out = destination / rel
        out.write_text(patch_source(out.read_text(), ami=rel.endswith('ami_usim.py')))
    adapter_out = destination / 'engine/nexvary_aka_backend.py'
    adapter_out.write_bytes(adapter_bytes)
    adapter_out.chmod(0o600)
    (destination / 'NEXVARY-AUDIT.json').write_text(json.dumps({
        'upstream_revision': PIN, 'source_sha256': HASHES,
        'modified_files': list(HASHES),
        'added_files': ['engine/nexvary_aka_backend.py'],
        'adapter_sha256': hashlib.sha256(adapter_bytes).hexdigest(),
        'gateway_verified': False, 'execution_reviewed': False,
        'limitations': ['No subscriber identity from sanitized phone reports',
                        'Remaining upstream networking, subprocesses, Asterisk, entrypoint scripts and dependencies require review',
                        'Engine authorization must be provisioned explicitly; no live AKA performed'],
    }, indent=2) + '\n')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    try:
        stage(args.source, args.destination)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, 'Staging refused: ' + str(exc) + '\n')

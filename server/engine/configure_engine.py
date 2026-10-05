"""Explicitly provision one engine credential; no service or gateway execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import uuid


def _directory(path):
    path = Path(path).absolute()
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            next_descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _private_file(directory, name, uid, gid):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != uid or info.st_gid != gid:
            raise ValueError('Existing panel files must be private and match the state owner.')
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _write_new(directory, name, content, uid, gid):
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        os.fchmod(descriptor, 0o600)
        if os.fstat(descriptor).st_uid != uid or os.fstat(descriptor).st_gid != gid:
            os.fchown(descriptor, uid, gid)
        with os.fdopen(descriptor, 'wb') as handle:
            descriptor = None
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        os.unlink(name, dir_fd=directory)
        raise


def configure(state_dir, config_path, device_id):
    if not isinstance(device_id, str) or str(uuid.UUID(device_id)) != device_id:
        raise ValueError('A canonical paired device UUID is required.')
    config_path = Path(config_path).absolute()
    if config_path.name in ('', '.', '..', 'password.json', 'phones.sqlite3', 'engine-token.sha256'):
        raise ValueError('Use a separate fresh engine configuration filename.')
    state = _directory(state_dir)
    parent = None
    try:
        info = os.fstat(state)
        if stat.S_IMODE(info.st_mode) != 0o700 or os.geteuid() not in (0, info.st_uid):
            raise ValueError('Panel state must be mode 0700 and owned by the authorized panel account.')
        uid, gid = info.st_uid, info.st_gid
        for name in ('password.json', 'phones.sqlite3'):
            descriptor = _private_file(state, name, uid, gid)
            os.close(descriptor)
        # Immutable read has no SQLite side effects. Refuse a pending WAL rather
        # than silently reading stale device authorization or creating sidecars.
        for name in ('phones.sqlite3-wal', 'phones.sqlite3-journal'):
            try:
                pending = os.stat(name, dir_fd=state, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if pending.st_size or stat.S_ISLNK(pending.st_mode):
                raise ValueError('Stop only the owned panel and allow pending database transactions to close before provisioning.')
        database_descriptor = _private_file(state, 'phones.sqlite3', uid, gid)
        try:
            with sqlite3.connect(f'file:/proc/self/fd/{database_descriptor}?mode=ro&immutable=1', uri=True) as database:
                if database.execute('SELECT 1 FROM devices WHERE device_id = ?', (device_id,)).fetchone() is None:
                    raise ValueError('The selected device is not currently paired.')
        finally:
            os.close(database_descriptor)
        parent = _directory(config_path.parent)
        parent_info = os.fstat(parent)
        if stat.S_IMODE(parent_info.st_mode) != 0o700 or parent_info.st_uid != os.geteuid():
            raise ValueError('Configuration parent must be mode 0700 and owned by the executing account.')
        for directory, name in ((state, 'engine-token.sha256'), (parent, config_path.name)):
            try:
                os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise ValueError('Existing credentials or symlinks are never overwritten.')
        token = secrets.token_urlsafe(32)
        config = json.dumps(dict(token=token, device_id=device_id)).encode() + b'\n'
        digest = hashlib.sha256(token.encode()).hexdigest().encode() + b'\n'
        _write_new(parent, config_path.name, config, os.geteuid(), os.getegid())
        try:
            _write_new(state, 'engine-token.sha256', digest, uid, gid)
        except Exception:
            os.unlink(config_path.name, dir_fd=parent)
            os.fsync(parent)
            raise
        os.fsync(parent)
        os.fsync(state)
    finally:
        os.close(state)
        if parent is not None:
            os.close(parent)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configure', action='store_true', required=True)
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--device-id', required=True)
    args = parser.parse_args()
    try:
        configure(args.state_dir, args.config, args.device_id)
    except Exception:
        # No exception/path/token/database payload is sent to logs.
        parser.exit(1, 'Engine provisioning refused; check ownership, private permissions, fresh paths and the paired device.\n')
    print('Engine credential provisioned privately. No service started. Restart only the owned panel to load its hash; gateway execution remains blocked.')

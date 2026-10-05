#!/usr/bin/env python3
"""Actual install/uninstall check for a disposable Ubuntu 24.04 GitHub-hosted runner.

Never run on the user's server. Passwords, cookies, hashes and installer output remain
in memory and are not printed or uploaded as artifacts.
"""
import errno
import json
import os
from pathlib import Path
import pty
import secrets
import select
import subprocess
import sys
import termios
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
APP = Path('/opt/nexvary-wifi-panel')
STATE = Path('/var/lib/nexvary-wifi-panel')
UNIT = Path('/etc/systemd/system/nexvary-wifi-panel.service')
SERVICE = 'nexvary-wifi-panel.service'
USER = 'nexvary-wifi-panel'
BASE = 'http://127.0.0.1:8787'


class SmokeFailure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise SmokeFailure(message)


def command(args, timeout=20):
    # Suppress all command output, including failure output, from CI logs.
    return subprocess.run(args, cwd=ROOT, capture_output=True, timeout=timeout, check=False)


def install_interactively(password):
    master, slave = pty.openpty()
    settings = termios.tcgetattr(slave)
    settings[3] &= ~termios.ECHO
    termios.tcsetattr(slave, termios.TCSANOW, settings)
    process = None
    prompts = [b'Admin password (at least 12 characters): ', b'Confirm password: ']
    seen = 0
    pending = b''
    deadline = time.monotonic() + 60
    try:
        process = subprocess.Popen(
            ['sudo', '-n', 'bash', 'server/install-panel.sh', '--install'],
            cwd=ROOT, stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
        )
        os.close(slave)
        slave = None
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.2)[0]:
                try:
                    block = os.read(master, 4096)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    block = b''
                if block:
                    pending = (pending + block)[-8192:]
                    if seen < len(prompts) and prompts[seen] in pending:
                        os.write(master, password.encode() + b'\n')
                        pending = b''
                        seen += 1
            if process.poll() is not None:
                require(seen == 2, 'Installer did not complete both password prompts.')
                require(process.returncode == 0, 'Installer exited unsuccessfully; output was withheld.')
                return
        raise SmokeFailure('Installer exceeded its 60-second deadline.')
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if slave is not None:
            os.close(slave)
        os.close(master)


def request(path, *, body=None, cookie=None):
    headers = {}
    data = None
    if body is not None:
        headers['Origin'] = BASE
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body).encode()
    if cookie:
        headers['Cookie'] = cookie
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.status, json.loads(response.read()), response.headers.get('Set-Cookie')


def state_digest():
    result = command(['sudo', '-n', 'sha256sum', str(STATE / 'password.json')])
    require(result.returncode == 0, 'Persistent password state is missing or unreadable.')
    return result.stdout.split()[0]


def archive_owned():
    result = command(['sudo', '-n', 'bash', 'server/uninstall-panel.sh', '--archive-owned'])
    require(result.returncode == 0, 'Owned panel archive failed; command output was withheld.')


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Run only in GitHub Actions.')
    require(os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'Run only on a disposable GitHub-hosted runner.')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    require(release.get('ID', '').strip('"') == 'ubuntu' and release.get('VERSION_ID', '').strip('"') == '24.04',
            'This check requires Ubuntu 24.04.')
    require(Path('/run/systemd/system').is_dir(), 'Actual running systemd is required.')
    require(not any(path.exists() or path.is_symlink() for path in (APP, STATE, UNIT)),
            'Refusing a runner with existing panel installation paths.')
    require(command(['getent', 'passwd', USER]).returncode != 0,
            'Refusing a runner with an existing panel user.')
    require(command(['getent', 'group', USER]).returncode != 0,
            'Refusing a runner with an existing panel group.')
    require(command(['sudo', '-n', 'true']).returncode == 0, 'Passwordless CI sudo is required.')
    password = secrets.token_urlsafe(32)
    cleaned = False
    try:
        install_interactively(password)
        require(command(['systemctl', 'is-active', '--quiet', SERVICE]).returncode == 0,
                'Installed panel service is not active.')
        user = command(['systemctl', 'show', '-p', 'User', '--value', SERVICE])
        require(user.stdout.decode().strip() == USER, 'Panel is not running under its dedicated unprivileged account.')
        identity = command(['id', '-u', USER])
        require(identity.returncode == 0 and identity.stdout.strip().isdigit() and identity.stdout.strip() != b'0',
                'Panel account must exist and must not be root.')
        deadline = time.monotonic() + 15
        while True:
            try:
                status, health, _ = request('/healthz')
                break
            except urllib.error.URLError:
                if time.monotonic() >= deadline:
                    raise SmokeFailure('Panel health endpoint did not become available.')
                time.sleep(0.2)
        require(status == 200 and health == {'panel': 'ok', 'gateway_verified': False},
                'Health endpoint must identify the panel without claiming gateway verification.')
        listeners = command(['ss', '-ltnH', 'sport = :8787'])
        addresses = [line.split()[3] for line in listeners.stdout.decode().splitlines()]
        require(addresses == ['127.0.0.1:8787'], 'Panel is not listening exclusively on IPv4 loopback.')
        try:
            request('/api/status')
            raise SmokeFailure('Unauthenticated status unexpectedly succeeded.')
        except urllib.error.HTTPError as error:
            require(error.code == 401, 'Unauthenticated status must require sign-in.')
        status, login, cookie = request('/api/login', body={'password': password})
        require(status == 200 and login.get('ok') is True and cookie is not None, 'Panel sign-in failed.')
        require('HttpOnly' in cookie and 'SameSite=Strict' in cookie, 'Session cookie protections are missing.')
        status, inventory, _ = request('/api/status', cookie=cookie.split(';', 1)[0])
        require(status == 200 and inventory.get('gateway_installed') is False, 'Panel status must not invent a deployment.')
        stages = inventory.get('stages', [])
        require(len(stages) == 8 and all(stage['status'] == 'not_tested' and stage['evidence'] is None for stage in stages),
                'Untested carrier stages must retain no fabricated evidence.')
        permissions = command(['sudo', '-n', 'stat', '-c', '%a:%U:%G', str(STATE / 'password.json')])
        require(permissions.stdout.decode().strip() == f'600:{USER}:{USER}', 'Password state permissions/ownership are incorrect.')
        before = state_digest()
        archive_owned()
        cleaned = True
        require(command(['systemctl', 'is-active', '--quiet', SERVICE]).returncode != 0,
                'Archived panel service is still active.')
        require(not APP.exists() and not UNIT.exists(), 'Owned application/unit was not archived.')
        require(STATE.is_dir() and state_digest() == before, 'Uninstall must preserve the original password state.')
        require(command(['getent', 'passwd', USER]).returncode == 0, 'Uninstall must preserve the service account.')
        print('Ubuntu 24.04 install, loopback health, authenticated inventory, unprivileged service, and preserving uninstall passed.')
    finally:
        # The initial existing-path guard establishes that this run owns any install.
        # On a failed assertion, stop only the marker/checksum-validated owned service.
        if not cleaned and (APP / '.nexvary-panel-owned').is_file():
            archive_owned()


if __name__ == '__main__':
    try:
        main()
    except SmokeFailure as error:
        print(f'Panel installation smoke check failed: {error}', file=sys.stderr)
        raise SystemExit(1)
    except Exception as error:
        # Avoid printing exception details that could contain request/credential data.
        print(f'Panel installation smoke check failed ({type(error).__name__}); sensitive output withheld.', file=sys.stderr)
        raise SystemExit(1)

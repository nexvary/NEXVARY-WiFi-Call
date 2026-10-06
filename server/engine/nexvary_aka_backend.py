"""Fail-closed transient AKA client; no SIM secret extraction or gateway execution.

The broker/phone must independently authorize each operation. This module alone
does not establish that Android permits authentication or that the gateway works.
"""
import http.client
import base64
import json
import os
import re
import socket
import stat
import struct
import time
import uuid


class AkaUnavailable(RuntimeError):
    pass


def _hex(value, lengths):
    if not isinstance(value, str) or len(value) not in lengths or not re.fullmatch(r'[0-9A-Fa-f]+', value):
        raise AkaUnavailable('Invalid AKA data.')
    return value.upper()


class _DeadlineSocket(socket.socket):
    """A fixed operation deadline also bounds slow HTTP headers/body reads."""
    def __init__(self):
        super().__init__(socket.AF_UNIX, socket.SOCK_STREAM)
        self.deadline = time.monotonic() + 35

    def _remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        self.settimeout(remaining)

    def connect(self, address):
        self._remaining()
        return super().connect(address)

    def recv_into(self, *args):
        self._remaining()
        return super().recv_into(*args)

    def sendall(self, *args):
        self._remaining()
        return super().sendall(*args)


def _peer_uid(sock):
    return struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))[1]


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=35)
        self.path = path

    def connect(self):
        path = self.path
        if not isinstance(path, str) or not path.startswith('/') or os.path.normpath(path) != path or path.startswith('//') or len(os.fsencode(path)) > 107:
            raise AkaUnavailable('Invalid private AKA socket configuration.')
        parts = path.split('/')[1:]
        directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        sock = None
        try:
            for component in parts[:-1]:
                descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = descriptor
            parent = os.fstat(directory)
            endpoint = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) != 0o700 or not stat.S_ISSOCK(endpoint.st_mode) or endpoint.st_uid != os.geteuid() or stat.S_IMODE(endpoint.st_mode) != 0o600:
                raise AkaUnavailable('Private AKA socket ownership or permissions invalid.')
            sock = _DeadlineSocket()
            # Hold the validated directory open across connection to avoid path replacement.
            sock.connect(f'/proc/self/fd/{directory}/{parts[-1]}')
            if _peer_uid(sock) != os.geteuid():
                raise AkaUnavailable('Private AKA peer unauthorized.')
            self.sock = sock
            sock = None
        finally:
            os.close(directory)
            if sock is not None:
                sock.close()


class PhoneAkaBackend:
    """Use a narrowly scoped loopback broker credential, never arbitrary URLs."""
    def __init__(self, token, device_id):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', token):
            raise AkaUnavailable('Invalid engine credential.')
        try:
            if str(uuid.UUID(device_id)) != device_id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise AkaUnavailable('Invalid selected device.') from None
        self._token = token
        self._device_id = device_id

    def __repr__(self):
        return '<PhoneAkaBackend: private credentials>'

    def identity(self):
        # The paired report intentionally contains no IMSI. Never invent one.
        raise AkaUnavailable('Real SIM identity is not available from this bridge.')

    def authenticate_ami(self, rand, autn):
        rand = _hex(rand, {32})
        autn = _hex(autn, {32})
        body = json.dumps(dict(device_id=self._device_id, rand=rand, autn=autn)).encode()
        connection = None
        try:
            unix_path = os.environ.get('NEXVARY_AKA_SOCKET')
            connection = (_UnixHTTPConnection(unix_path) if unix_path is not None
                          else http.client.HTTPConnection('127.0.0.1', 8787, timeout=35))
            # Direct connection: no environment proxy, redirects, query secrets or retries.
            connection.request('POST', '/api/engine/aka', body=body, headers={
                'Authorization': 'Bearer ' + self._token,
                'Content-Type': 'application/json', 'Accept': 'application/json',
            })
            response = connection.getresponse()
            if response.status != 200 or response.getheader('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise AkaUnavailable('Authorized phone authentication unavailable.')
            raw = response.read(4097)
            if len(raw) > 4096:
                raise AkaUnavailable('Invalid AKA response.')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise AkaUnavailable('Invalid AKA response.')
            if set(result) != {'state', 'payload'} or result['state'] not in ('SUCCESS', 'SYNC_FAILURE'):
                raise AkaUnavailable('Authorized phone authentication unavailable.')
            payload = result['payload']
            if not isinstance(payload, str) or len(payload) > 128:
                raise AkaUnavailable('Invalid AKA response.')
            data = base64.b64decode(payload, validate=True)
            if base64.b64encode(data).decode() != payload:
                raise AkaUnavailable('Invalid AKA response.')
            if result['state'] == 'SUCCESS' and len(data) >= 2 and data[0] == 0xDB:
                res_length = data[1]
                ck_start = 2 + res_length
                ik_start = ck_start + 17
                if not 4 <= res_length <= 16 or len(data) != res_length + 36 or data[ck_start] != 16 or data[ik_start] != 16:
                    raise AkaUnavailable('Invalid AKA response.')
                return data[2:ck_start].hex().upper(), data[ck_start+1:ik_start].hex().upper(), data[ik_start+1:].hex().upper(), None
            if result['state'] == 'SYNC_FAILURE' and len(data) == 16 and data[:2] == b'\xdc\x0e':
                return None, None, None, data[2:].hex().upper()
            raise AkaUnavailable('Invalid AKA response.')
        except AkaUnavailable:
            raise
        except Exception:
            # Never include a response, challenge, credential or original exception.
            raise AkaUnavailable('Authorized phone authentication unavailable.') from None
        finally:
            if connection is not None:
                connection.close()

    def authenticate(self, rand, autn):
        res, ck, ik, auts = self.authenticate_ami(rand, autn)
        # Upstream first-attach SWu encodes synchronization failure as (AUTS, None, None).
        # Its reauthentication path refuses AUTS; this patch does not invent support.
        return (auts, None, None) if auts is not None else (res, ck, ik)


def get_backend():
    """Read private engine authorization, never a long-term SIM secret."""
    path = os.environ.get('NEXVARY_ENGINE_AUTH_FILE')
    if not path:
        raise AkaUnavailable('Engine authorization is not configured.')
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid() or info.st_size > 4096:
            raise AkaUnavailable('Engine authorization must be a private owned regular file.')
        with os.fdopen(descriptor, 'r', encoding='utf-8') as handle:
            descriptor = None
            config = json.load(handle)
        if not isinstance(config, dict) or set(config) != {'token', 'device_id'}:
            raise AkaUnavailable('Invalid engine authorization.')
        return PhoneAkaBackend(config['token'], config['device_id'])
    except AkaUnavailable:
        raise
    except Exception:
        raise AkaUnavailable('Engine authorization unavailable.') from None
    finally:
        if descriptor is not None:
            os.close(descriptor)

"""Asterisk ARI control adapter. SIP registration/media remain in res_pjsip.

No arbitrary URLs, channels, contexts or CLI commands are accepted from callers.
Loopback HTTP is permitted only for a co-located isolated PBX; remote ARI needs
certificate-verified HTTPS (with optional client certificate).
"""
import base64
import ipaddress
import json
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, ProxyHandler, HTTPRedirectHandler
from .calls import Calls, Route, State


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AriAdapter:
    def __init__(self, base_url, username, password, ca_file=None, client_cert=None, client_key=None):
        parsed = urlsplit(base_url)
        local = False
        try:
            local = ipaddress.ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            pass
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/ari")
                or (parsed.scheme == "http" and not local)):
            raise ValueError("ARI must use HTTPS or numeric loopback HTTP")
        if not username or not password:
            raise ValueError("ARI credentials required")
        context = ssl.create_default_context(cafile=ca_file)
        if client_cert:
            context.load_cert_chain(client_cert, client_key)
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
        self.base = base_url.rstrip("/") + ("" if parsed.path == "/ari" else "/ari")
        self.authorization = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()

    def request(self, method, path, parameters=None):
        url = self.base+path
        if parameters:
            url += "?"+urlencode(parameters)
        request = Request(url, method=method, headers={"Authorization": self.authorization, "Accept": "application/json"})
        try:
            with self.opener.open(request, timeout=5) as response:
                raw = response.read(1024*1024+1)
                if len(raw) > 1024*1024:
                    raise RuntimeError("PBX response exceeds limit")
                return json.loads(raw) if raw else None
        except (HTTPError, URLError) as exc:
            # Avoid copying request URLs, credential-bearing headers or upstream bodies.
            raise RuntimeError("PBX operation failed") from None

    def originate_internal(self, call, source_extension):
        if call.route != Route.INTERNAL or not re.fullmatch(r"[1-9][0-9]{3,5}", source_extension):
            raise PermissionError("Only internal call origination is provisioned")
        if not re.fullmatch(r"[1-9][0-9]{3,5}", call.target):
            raise PermissionError("Invalid destination")
        # Ring the authenticated owner's endpoint, then dial its allowed peer via
        # its dedicated context. No Stasis consumer is needed for this dialplan path.
        return self.request("POST", "/channels", {
            "endpoint": "PJSIP/"+source_extension,
            "extension": call.target, "context": "user-"+source_extension,
            "priority": 1, "channelId": call.id, "timeout": 30,
        })

    def hangup(self, channel_id):
        if not re.fullmatch(r"[a-f0-9]{32}", channel_id):
            raise ValueError("Invalid channel ID")
        return self.request("DELETE", "/channels/"+channel_id)

    def channel_state(self, channel_id):
        if not re.fullmatch(r"[a-f0-9]{32}", channel_id):
            raise ValueError("Invalid channel ID")
        return self.request("GET", "/channels/"+channel_id)


class InternalController:
    """Trusted local controller; caller identity must come from authenticated service."""
    def __init__(self, calls: Calls, pbx: AriAdapter, owner_extensions: dict[str, str]):
        self.calls, self.pbx, self.owner_extensions = calls, pbx, dict(owner_extensions)
        self.pending_hangups = set()

    def originate(self, owner, target):
        source = self.owner_extensions.get(owner)
        if source is None:
            raise PermissionError("No registered SIP account")
        call = self.calls.start(owner, target, Route.INTERNAL)
        try:
            self.pbx.originate_internal(call, source)
        except Exception:
            self.calls.transition(call.id, State.FAILED, "pbx_unavailable")
            raise
        return call

    def hangup(self, owner, call_id):
        call = self.calls.calls[call_id]
        if call.owner != owner:
            raise PermissionError("Call belongs to another user")
        self.pbx.hangup(call.id)
        self.calls.transition(call.id, State.ENDED)

    def tick(self):
        self.pending_hangups.update(self.calls.terminate_due())
        for call_id in list(self.pending_hangups):
            try:
                self.pbx.hangup(call_id)
            except RuntimeError:
                continue  # Retry next tick, never silently abandon teardown.
            self.pending_hangups.discard(call_id)

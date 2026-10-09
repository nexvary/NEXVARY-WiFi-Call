#!/usr/bin/env python3
"""Generate a private standalone PBX config directory; never edit host services.

Run only after reviewing server preflight. No cellular routes are generated.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets


def generate(output, bind="127.0.0.1", extensions=("1001", "1002"), external_address=None, local_net=None):
    ipaddress.IPv4Address(bind)
    if external_address:
        ipaddress.IPv4Address(external_address)
    if local_net:
        ipaddress.IPv4Network(local_net)
    if len(set(extensions)) != len(extensions) or not 2 <= len(extensions) <= 100:
        raise ValueError("Use between 2 and 100 unique extensions")
    if any(not re.fullmatch(r"[1-9][0-9]{3,5}", e) for e in extensions):
        raise ValueError("Invalid extension")
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    credentials = {e: secrets.token_urlsafe(32) for e in extensions}
    ari_secret = secrets.token_urlsafe(32)
    pjsip = f"""; NEXVARY standalone private PBX. No UDP transport or anonymous endpoint.
[global]
type=global
endpoint_identifier_order=username,auth_username

[secure-tls]
type=transport
protocol=tls
bind={bind}:5061
cert_file=/etc/asterisk/tls/fullchain.pem
priv_key_file=/etc/asterisk/tls/privkey.pem
method=tlsv1_2
verify_server=yes
"""
    if external_address:
        pjsip += f"external_signaling_address={external_address}\nexternal_media_address={external_address}\n"
    if local_net:
        pjsip += f"local_net={local_net}\n"
    dialplan = "; Only explicit internal peers; no international/PSTN/emergency routes.\n"
    for extension, password in credentials.items():
        pjsip += f"""
[{extension}]
type=endpoint
transport=secure-tls
context=user-{extension}
disallow=all
allow=ulaw,alaw
auth=auth-{extension}
aors={extension}
direct_media=no
media_encryption=sdes
media_encryption_optimistic=no
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes
rtp_timeout=60
rtp_timeout_hold=120
allow_transfer=no

[auth-{extension}]
type=auth
auth_type=userpass
username={extension}
password={password}

[{extension}]
type=aor
max_contacts=1
remove_existing=no
minimum_expiration=60
maximum_expiration=600
qualify_frequency=30
"""
        dialplan += f"\n[user-{extension}]\n"
        for peer in extensions:
            if peer == extension:
                continue
            dialplan += f"""exten => {peer},1,Set(GROUP()={extension})
 same => n,GotoIf($[${{GROUP_COUNT({extension})}} > 1]?busy)
 same => n,Set(TIMEOUT(absolute)=330)
 same => n,Dial(PJSIP/{peer},30,L(300000))
 same => n,Hangup()
 same => n(busy),Busy(1)
 same => n,Hangup()
"""
    files = {
        "pjsip.conf": pjsip, "extensions.conf": dialplan,
        "rtp.conf": "[general]\nrtpstart=20000\nrtpend=20100\nstrictrtp=yes\n",
        "http.conf": "[general]\nenabled=yes\nbindaddr=127.0.0.1\nbindport=8089\n",
        "ari.conf": f"[general]\nenabled=yes\npretty=no\n[nexvary-control]\ntype=user\nread_only=no\npassword={ari_secret}\n",
        "manager.conf": "[general]\nenabled=no\n",
        "modules.conf": "[modules]\nautoload=yes\nnoload=chan_sip.so\nnoload=chan_iax2.so\nnoload=chan_dongle.so\nnoload=res_hep.so\n",
        "logger.conf": "[general]\n[logfiles]\nconsole=warning,error,notice\nmessages=warning,error,notice\n",
        "cdr.conf": "[general]\nenable=yes\n",
        "cdr_custom.conf": "[mappings]\nMaster.csv => ${CSV_QUOTE(${CDR(start)})},${CSV_QUOTE(${CDR(src)})},${CSV_QUOTE(${CDR(dst)})},${CDR(billsec)},${CSV_QUOTE(${CDR(disposition)})},${CSV_QUOTE(${CDR(uniqueid)})}\n",
        "accounts.json": json.dumps({"transport": "tls", "port": 5061, "srtp": "required", "accounts": credentials, "ari_user": "nexvary-control", "ari_secret": ari_secret}, indent=2)+"\n",
    }
    for name, content in files.items():
        fd = os.open(output/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--extensions", nargs="+", default=["1001", "1002"])
    parser.add_argument("--external-address")
    parser.add_argument("--local-net")
    args = parser.parse_args()
    generate(args.output, args.bind, args.extensions, args.external_address, args.local_net)
    print("Private configuration created; accounts.json contains credentials. No service was modified.")

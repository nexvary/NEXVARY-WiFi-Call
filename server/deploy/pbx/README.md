# Independent NEXVARY SIP PBX

This is an additive SIP/media path. It does not require AKA, ePDG, IMS, a modem,
or changes to Outline. Asterisk owns SIP transactions, codec negotiation and
encrypted media; the Python multipath module owns independent call policy and
trusted control adapters. It is not a home-grown SIP server.

## What is runnable

`generate.py` creates private standalone PJSIP configurations with independently
generated account secrets, SIP TLS on 5061, mandatory SDES-SRTP, PCMU/PCMA, exact
internal destination allowlists, one registration per account, no anonymous
endpoint, no unencrypted SIP transport, no transfer, per-origin concurrent call
limit and a five-minute media limit. Only extensions 1001 and 1002 exist by
default. ARI is loopback-only on 8089 and AMI is disabled. No PSTN, international,
premium or emergency route exists. Nothing installs or starts automatically.

```bash
python3 server/deploy/pbx/generate.py --output /path/to/private-new-config
PYTHONPATH=server python3 -m unittest multipath.test_calls -v
```

The generated `accounts.json` is sensitive. Provision each user only their own
account, using an authenticated administrative channel. Never publish it as a
download artifact. A TLS certificate valid for the configured host/IP and a
matching private key must be mounted at `/etc/asterisk/tls/`; production clients
must validate that certificate. A private CA requires deliberate trust setup.

Default binding is loopback so generation cannot create a public listener.
After host preflight and approved isolation, use `--bind` for a dedicated private
IPv4 address. For a NAT deployment also pass `--external-address` and `--local-net`
with verified IPv4 settings. SRTP UDP 20000–20100 must travel over the selected
network. No firewall edits are performed. A container bridge needs correct
signalling/media addresses and allowed RTP traffic; TLS alone does not resolve
NAT or prevent denial of service. Isolated private/VPN access is the initial
deployment choice. Public exposure needs restricted firewall/rate-limit policy.

## Synthetic live integration

`scripts/pbx_ci.sh` runs a separate Asterisk process with temporary directories,
temporary trusted certificate and synthetic secrets. It never writes `/etc`,
changes a firewall, or stops another service. It requires an otherwise disposable
Linux CI runner with Asterisk installed and `pylibsrtp` available. Port conflicts
fail rather than changing a current service.

```bash
# Disposable CI runner prerequisites, not a production-server deployment command:
sudo apt-get update
sudo apt-get install -y asterisk libsrtp2-dev
python3 -m pip install pylibsrtp==1.0.0
bash scripts/pbx_ci.sh
```

The harness uses two real TLS SIP connections, digest challenge registration,
authenticated outgoing INVITE, incoming ringing/answer, ACK, two independently
encrypted SRTP streams, authenticated decryption in both directions and BYE.
Its output labels this as synthetic PBX evidence. It is not an Android audio
test, an acoustic quality test, a NAT test or a cellular call test. No live success
is claimed until the CI process passes. Unit tests are separate policy evidence.

## Optional standalone container after preflight review

The Dockerfile uses Ubuntu 24.04's Asterisk 20 package, verified against the
[Ubuntu source package listing](https://packages.ubuntu.com/source/noble/asterisk).
The image build refuses another major version and permits patched distro
revisions. This is a reproducible recipe, not a claim that Docker was exercised
on your server. Compose creates a separate project/network/volumes, drops all
capabilities, runs as UID 10001, makes the root filesystem read-only, does not
publish ARI, and has no host networking, USB device passthrough or privileged
mode. Certificate/key mounts are individual read-only files. Default published
SIP/media ports bind only the host loopback address.

After a clean preflight, choose a new private directory and prepare the config
and trusted certificate. For this container only, generation must bind its
internal SIP listener to `0.0.0.0`; host reachability still follows the explicit
Compose bind address. Set `--external-address` to the selected host IPv4 address
and `--local-net` to the actual isolated container subnet for NAT. Do not guess
the subnet, certificate name, or public address. Ensure UID 10001 can read the
private config/key without making them world-readable; all these files belong
only to this new PBX. Set the absolute file paths from `.env.example` in a private
environment file. These commands build/configure without starting a listener:

```bash
docker compose --env-file /path/to/private-pbx.env -f server/deploy/pbx/compose.yml config --quiet
docker compose --env-file /path/to/private-pbx.env -f server/deploy/pbx/compose.yml build
```

Only when resources, ports, DNS/TLS, NAT, access policy and isolation have been
reviewed, explicitly start it:

```bash
docker compose --env-file /path/to/private-pbx.env -f server/deploy/pbx/compose.yml up -d
docker compose --env-file /path/to/private-pbx.env -f server/deploy/pbx/compose.yml ps
```

These commands do not restart existing services or alter firewall rules.
Docker itself creates its usual network/published-port rules, so review Docker
and Outline networks in preflight first. Do not install Docker blindly on an
existing server. Loopback publications are a local test default; Android needs
a deliberately selected reachable private interface and matching certificate.
The default resource limits are laboratory bounds, not a measured capacity.
If the host cannot spare them, run this PBX/voice gateway on a separate machine.

## Cellular voice boundary

`multipath.calls.VoiceEvidence` requires fresh independent observations of SIM,
network registration, voice commands, audio interface, both call directions and
two-way audio. Mere modem AT/APDU success cannot satisfy this gate. A policy also
requires an explicit E.164 destination allowlist, positive cost estimate, worst-case
budget reservation, maximum duration and concurrency. No cellular dialplan is
generated, and ARI origination currently refuses cellular requests. The cellular
state/policy engine is ready for a separately verified SIP voice gateway adapter;
there is no claim that a USB modem audio driver is already implemented.

Control state alone cannot tear down audio: `InternalController.tick()` retries
failed PBX hangups, and generated internal dialplans enforce their own duration.
Cellular routes must enforce duration and destination restrictions independently
at the hardware-side gateway before activation. Memory policy/CDR state is for
the isolated laboratory; durable transactional budget storage is required before
paid cellular service. Asterisk CDR CSV uses its own volume/log directory and
must be retained privately with limited access. These are not billing guarantees.

Huawei K3770 21.023.04.00.11 / 12D1:14C9 stays unverified for voice/audio. No
`chan_dongle` module is loaded or assumed compatible. A local hardware gateway
in a place with cellular coverage can register as an authenticated SIP trunk
after its audio path and carrier authorization are established. A VPS cannot
physically host a USB modem that remains beside the user.

## Upstream and license boundary

Configurations are original NEXVARY configuration, not copied implementation.
Architecture uses upstream [PJSIP endpoint relationships](https://docs.asterisk.org/Configuration/Channel-Drivers/SIP/Configuring-res_pjsip/PJSIP-Configuration-Sections-and-Relationships/),
[secure calling](https://docs.asterisk.org/Deployment/Secure-Calling/Secure-Calling-Tutorial/)
and [ARI channel API](https://docs.asterisk.org/Latest_API/API_Documentation/Asterisk_REST_Interface/Channels_REST_API/).
Asterisk is an external service; review its GPLv2 distribution obligations and
each installed optional module before distributing runtime binaries. `pylibsrtp`
(BSD-3-Clause) wraps libsrtp (BSD-3-Clause) only in the synthetic test runner.
FreePBX/FreeSWITCH/chan_dongle sources are not copied or bundled. The Linux distro
package version must be recorded by CI; no compatibility claim extends to every
Asterisk version or every modem firmware.

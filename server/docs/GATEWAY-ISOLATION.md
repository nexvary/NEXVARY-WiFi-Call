# Gateway isolation preparation

This stage verifies prerequisites and supplies a private AKA transport. It does not unlock carrier privileges, provide a real subscriber identity, start the upstream engine or establish ePDG/IMS/calling evidence.

## Why native execution stays blocked

The pinned upstream gateway can install split default routes, replace policy routing table 51820, create/delete named namespaces and change DNS. Cleanup can restore an old resolver backup even when this run did not write DNS. Its original entry point enables SIP logging and starts additional readers/helpers. Running this directly on the shared Outline/FG MTM host is not an acceptable deployment.

The source staging gate remains active. Its `--netns` option does not isolate every process or the filesystem. A full network namespace isolates interfaces/routes/sockets; a private mount namespace is also necessary for resolver and configuration writes. Protocol code, dependencies, resource ownership and cleanup still require review before a runnable engine is allowed.

## Explicit isolation probe

After pulling `dev/foundation`, first print the plan:

```bash
cd ~/nexvary-wifi-panel
git pull --ff-only origin dev/foundation
python3 server/engine/isolation_probe.py
```

On the actual Ubuntu host, the explicit probe requires sudo and existing `unshare`, `mount` and `ip` tools:

```bash
sudo python3 server/engine/isolation_probe.py --probe
```

It creates temporary private network, mount and PID namespaces with private mount propagation. There are no external interfaces or egress routes. It binds a temporary resolver file inside the private mount namespace, writes a synthetic marker there, and verifies the host resolver, routes, rules and namespaces are unchanged after exit. It starts no gateway, opens no carrier connection, changes no host firewall or routes, and creates no persistent named network namespace. The loopback panel must be unreachable from the empty private network namespace. A failed or unsupported check is not a successful isolation result.

The CI smoke test additionally starts synthetic host TCP/Unix sentinels on a disposable Ubuntu 24.04 runner. It proves host loopback isolation and private Unix communication across the namespace boundary while the host sentinel remains reachable. It contains no SIM authentication or production service credentials. CI evidence does not replace this probe and existing-service health checks on the actual VPS.

## Private AKA transport

`aka_unix_relay.py` is a separately started, opt-in host-side relay. Its private Unix socket uses a fresh owned directory with mode 0700 and socket mode 0600, checks Linux peer UID, accepts only the exact authenticated AKA route, bounds workers/frames/timeouts and forwards to the fixed host loopback panel. It logs no credentials, challenges or result material. It installs no service, publishes no TCP port and never authenticates a SIM itself.

The engine adapter can explicitly use `NEXVARY_AKA_SOCKET` rather than assuming the host panel is reachable at loopback inside a full network namespace. Both processes must have the authorized same UID and a private filesystem path available inside the mount namespace. Invalid Unix configuration fails closed and does not fall back to HTTP. Independent engine authorization and an explicit foreground phone session remain mandatory. See [engine transport/provisioning](../engine/README.md).

## Remaining prerequisites

1. The actual selected phone/SIM must grant the application carrier privileges before its public ICC authentication API can be called. Pairing and server connectivity cannot grant this permission. Otherwise an independently authorized alternative SIM authentication backend is required.
2. A genuine authorized subscriber identity/NAI and actual carrier configuration must be supplied. Diagnostic reports deliberately do not contain an IMSI.
3. Review and replace remaining privileged shell commands, unsafe namespace/resource cleanup, DNS restoration, entry-point logging and unpinned dependencies. Keep these mutations inside fully isolated owned resources.
4. Add reviewed egress for one lightweight SWu process and measure resource use on the real host before introducing Asterisk, IMS, SIP/RTP ports or audio.
5. Verify ePDG, authentication, IMS registration, outbound, inbound and audio independently using actual evidence. No fixed RES/CK/IK, fabricated subscriber identity or extracted long-term SIM secret is permitted.

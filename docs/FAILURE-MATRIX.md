# Failure Matrix

| Condition | Product state | User action | Engineering behavior |
|---|---|---|---|
| No Wi-Fi | DEGRADED | Connect to Wi-Fi | no carrier probe |
| Wi-Fi captive portal | DEGRADED | Sign in to Wi-Fi | wait for validated network |
| Wi-Fi not validated | DEGRADED | Check internet | do not infer carrier failure |
| VPN active | DEGRADED/INFO | Retry without VPN if path fails | record transport context |
| Multiple SIMs | UNKNOWN until selected | Select SIM | subscription-scoped evaluation |
| No carrier privilege | RESTRICTED | Use system WFC/settings or another authorized path | no hidden API workaround |
| Carrier evidence absent | UNKNOWN | Run diagnostics | never label supported |
| ePDG DNS absent | path-specific failure | retry/change network | do not mark whole carrier unsupported |
| Gateway unavailable | DEGRADED | reconnect gateway | fall through only to configured safe path |
| SIP absent | no SIP fallback | configure provider if desired | never fabricate credentials |
| Permission denied | RESTRICTED | explain optional permission | graceful degradation |
| Background restricted | DEGRADED | allow required runtime mode | no polling loop |
| Call quality poor | DEGRADED | improve Wi-Fi | preserve metrics and path |
| Emergency number | BLOCKED in experimental app-controlled modes | use system emergency calling | never route experimentally |

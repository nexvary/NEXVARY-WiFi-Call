# Research baseline

## Standards
Primary interoperability target: GSMA IR.51 (IMS voice/video/SMS over untrusted Wi-Fi) and the referenced 3GPP IMS/SWu specifications.

## Open-source references
### pagecat/vowifi_gateway
Useful evidence that a real VoWiFi-to-SIP gateway can be built with a Linux host, PC/SC SIM reader, userspace IKEv2/EAP-AKA/ESP and an IMS-capable Asterisk/PJSIP stack. Treat as a reference implementation, not proof that arbitrary Android apps can access carrier IMS.

### boa-z/vowifi-go
Strong protocol/library reference. Its documented surface includes SIM/ISIM AKA, IKEv2/EAP-AKA/AKA', ESP/TUN/XFRM, ePDG, IMS registration/security agreement, SMS/USSD, SIP voice and RTP/SRTP. Upstream explicitly states that real modem/SIM/ePDG/IMS validation and production hardening remain incomplete.

## Key conclusion
The hard problem is not audio quality or a dialer UI. It is authorized subscriber authentication plus carrier-specific SWu/IMS interoperability. Therefore carrier compatibility is evidence-driven and isolated from the UI.

## Android constraint
The app must not assume that public Android APIs allow a third-party APK to become the carrier IMS implementation. Native mode is capability-detected. Unsupported devices fall back only to explicitly configured, lawful gateway/SIP modes.

## Research priorities
1. Android public API capability matrix by API level/OEM.
2. Real SIM/modem lab harness.
3. ePDG discovery and IPv4/IPv6/NAT-T behavior.
4. EAP-AKA/AKA' and synchronization recovery.
5. IMS REGISTER + Security-Agree + P-CSCF failover.
6. AMR-WB/EVS where legally/licensably available; Opus for SIP fallback.
7. RTP jitter buffer, packet-loss concealment, echo/noise handling and handover metrics.
8. Carrier-by-carrier evidence fixtures with all subscriber secrets redacted.

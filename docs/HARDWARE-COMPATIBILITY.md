# Cellular voice / USIM hardware evidence — 2026-10-09

This is a candidate assessment, not field certification. No modem, SIM or
Egyptian carrier was physically available in the build environment. USB data,
network-unlocked status, signal and SIM-ready status do not prove calling.

## Owner's actual hardware

There is one Huawei K3770, firmware `21.023.04.00.11`, USB ID observed
`12D1:14C9`; E153 is not an additional owned modem. USB repository retains the
owner-supplied COM5/COM7 reports. AT worked; card status/file access and fixed
SELECT MF have historical evidence. CCHO/CGLA timed out in recorded probes.
That timeout is inconclusive. Voice, two-way audio, real AKA, ePDG authentication,
IMS registration and mobile calls are **not verified**. Keep diagnostics enabled;
never flash unknown firmware or declare permanent lack of support from timeout.

## Candidates

| Exact candidate | Voice / audio / commands | Linux / Asterisk integration | Radio and firmware | Confidence for NEXVARY |
|---|---|---|---|---|
| Huawei E1550 / E155X | chan_dongle maintainer fork lists E155X as a candidate for voice; exact SKU audio and firmware unverified | Historical UMTS channel driver; Linux serial and audio interfaces must both be observed; no current Asterisk build/load test here | Exact bands/2G/3G require SKU datasheet. No verified 4G/VoLTE evidence obtained | Low; not a purchase certification |
| Huawei E1750 / E175X | Same source lists E175X; must demonstrate outgoing/incoming AT call control and usable audio on exact unit | Same unverified driver/ABI conditions | Exact regional bands and voice-enabled firmware unknown; do not infer VoLTE from a sales listing | Low |
| Huawei E173 | No exact current manufacturer voice/firmware source established in this review | Third-party reports alone do not certify a driver or audio path; bench test required | Exact SKU bands and firmware unknown; no proven 4G/VoLTE | Low |
| SIMCom SIM7600E-H | Manufacturer lists VoLTE, Linux drivers and optional PCM; USB AUDIO application note and AT manual listed. Exact board/audio mode must be confirmed | AT control adapter plus actual bidirectional audio integration required; neither chan_dongle nor PBX integration is automatic | LTE FDD B1/3/5/7/8/20, TDD B38/40/41; WCDMA B1/5/8; GSM 900/1800. VoLTE provisioning/firmware gate remains | Medium for a bench candidate; unverified system integration |
| Quectel EC25-E / EC25-EUX | 2026 manufacturer specification lists PCM and optional VoLTE; vendor forum confirms ATD/ATA/ATH call control and separate audio requirement | Manufacturer lists Linux serial drivers; PBX needs verified USB/PCM media transport and exact firmware configuration | E: FDD B1/3/5/7/8/20. EUX: B1/3/7/8/20/28A. Both TDD B38/40/41, GSM B3/8; WCDMA E B1/5/8, EUX B1/8 | Medium for a voice-capable exact SKU; not approved Egyptian VoLTE |

Manufacturer sources: [SIM7600X-H product and downloads](https://en.simcom.com/product/SIM7600X-H.html),
[EC25 specification V3.0](https://www.quectel.com/content/uploads/2026/03/Quectel_EC25_Series_LTE_Standard_Module_Specification_V3.0.pdf),
[Quectel voice/RIL explanation](https://forums.quectel.com/t/voice-call-support-on-ec25-e-with-android-ril-driver/32988/2).
Historical Huawei candidate source: [chan_dongle maintainer fork](https://github.com/phcoder/asterisk-chan-dongle-1).
Its claimed Asterisk 14+ support and sample 13.7 build do not prove compatibility
with modern Asterisk releases. No voice-enabling/unlock/reset commands from its
examples are executed or recommended automatically.

An EC25 family name is insufficient: the specification includes explicitly
data-only variants. PCM may require a codec and correctly routed board pins;
USB serial is not USB audio. Obtain the vendor's exact firmware revision,
audio application note and carrier provisioning confirmation before purchase.
SIM7600E-H or EC25-E/EUX development boards with documented audio are better
bench candidates than an unidentified legacy stick; this is an engineering
assessment, not a guaranteed working product recommendation.

## Egypt

[NTRA's January 2025 approved-equipment list](https://www.tra.gov.eg/wp-content/uploads/2025/01/1st-Jan.-2025.pdf)
contains Huawei E1550/E1750/E173 descriptions. Type approval does not certify
voice-enabled firmware, SIP gateway legality or present carrier interoperability.
No current exact operator band plan or modem VoLTE whitelist was verified in
this review. Egyptian suitability remains conditional on actual local coverage,
supported bands, SIM plan, exact firmware/operator profile and written permission.
European Vodafone certification is not Vodafone Egypt certification.

## Engine and license assessment

| Project | Source / license evidence | Integration decision |
|---|---|---|
| Asterisk | [Official license information](https://docs.asterisk.org/About-the-Project/License-Information/): GPLv2 plus alternative commercial licensing | Separate authenticated SIP/PBX process; preserve notices and corresponding-source obligations when distributing |
| FreePBX | [Framework release/17.0 LICENSE](https://github.com/FreePBX/framework/blob/release/17.0/LICENSE): GPLv3; modules have individual terms | Optional administration layer, not necessary for first internal-call path; no source bundled |
| chan_dongle | [Maintainer fork license](https://github.com/phcoder/asterisk-chan-dongle-1/blob/master/LICENSE.txt); upstream wdoekes URLs could not be retrieved in this research environment | No binary bundled; pin exact revision, inspect all file licenses, build and load against exact PBX ABI, then physical audio/call tests before enabling |
| RasPBX | [Project site](https://www.raspberry-asterisk.org/) could not be retrieved | Historical distribution reference only; no claim about newest version/support or license of an unavailable image; do not install legacy image over Ubuntu |
| Osmocom OsmoSIPConnector | [Official mirror](https://github.com/osmocom/osmo-sip-connector): AGPL-3.0, MNCC-to-SIP for OsmoMSC | Not a drop-in retail USB voice modem adapter; private cellular infrastructure is outside this deployment |
| Modern GSM-SIP Bridge | [selvakn/gsm-sip-bridge](https://github.com/selvakn/gsm-sip-bridge): GPL-3.0 label plus contradictory explicit non-commercial-use statement in README | No copying/bundling/deployment pending clarification. Upstream default privileged host-network container would also violate intended shared-server isolation |

## Physical acceptance before a route is Available

Record exact model/firmware/USB interfaces and operator (without identifiers),
demonstrate authorized local outgoing and incoming calls, then verify bidirectional
audio for at least one call over SIP TLS/SRTP. Test SIM removal, modem busy,
coverage loss, USB unplug, NAT and reconnection. Capture timestamps, endpoints,
transport/codec, duration and outcome without subscriber/authentication secrets.
USIM AKA uses independently scoped consent and a carrier-authorized challenge;
synthetic challenge tests never certify real carrier authentication.

A local Linux device in a place with coverage hosts the physical modem; the VPS
hosts control/PBX where appropriate. No physical USB connection to a cloud VPS
is assumed. A commercially supported SIP cellular gateway can avoid unsupported
USB audio/chan_dongle combinations, but its exact TLS/SRTP support, carrier
compatibility and Egyptian authorization still need verification.

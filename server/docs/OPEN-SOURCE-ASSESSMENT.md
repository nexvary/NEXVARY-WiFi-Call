# Open-source gateway assessment

Checked 2026-10-05 against public upstream repositories and their current remote HEADs. This session integrates no third-party protocol source into NEXVARY. References inform the next PoC; upstream assertions of carrier compatibility are not NEXVARY verification.

| Project | Remote HEAD checked | License / assessment | Next use |
|---|---|---|---|
| [pagecat/vowifi_gateway](https://github.com/pagecat/vowifi_gateway) | `e3719840b93961f933aab3dac8bd2641936e2bcc` | MIT top-level; separate dependency licenses. Container engine plus native/privileged control modes. PC/SC AKA implementation exists alongside software-key paths and unsafe diagnostic/fallback behavior. | First candidate for a pinned, fail-closed, key-log-free audit; see [PoC gates](GATEWAY-POC.md). No install yet. |
| [boa-z/vowifi-go](https://github.com/boa-z/vowifi-go) | `1e9c6e6adbfcd9667695149d5ecb0f71cd062f07` | AGPL-3.0; experimental Go SIM/AKA, SWu and IMS runtime. Upstream states feature/production/carrier gaps remain. | Protocol architecture and tests reference. Evaluate license/source obligations and carrier behavior before selecting it as runtime. |
| [hw5773/vowifi-ue-testing-framework](https://github.com/hw5773/vowifi-ue-testing-framework) | `0c753a0cccf3c456c47377709ff24dfc49035717` | No root license identified or license metadata returned. Testbed includes ePDG/HSS/IMS/controller/testcases. | Read as research reference; do not copy or redistribute unlicensed code. Whole testbed is unsuitable as the first 1 GiB VPS PoC. |
| [selvakn/gsm-sip-bridge](https://github.com/selvakn/gsm-sip-bridge) | `e9a653c6a3eb41780958482759c83e5b304b1191` | GPL-3.0 license file; README additionally says no commercial product/service/deployment. Rust/Linux bridge offers modem/PCSC VoWiFi/VoLTE paths. | Hold code adoption until the README/license discrepancy and bundled dependencies are clarified; operations/evidence separation remain useful references. Avoid its full monitoring stack on 1 GiB. |
| [phhusson/ims](https://github.com/phhusson/ims) | `c180bdff810880d8f75f5dda70e6bcbee6991e9e` | GPL-2.0 root license. Platform/custom-ROM IMS integration includes platform keys and framework dependencies. | IMS/SIP reference only; platform keys, privileged deployment and patches are outside the consumer APK scope. |
| [AOSP IMS / Telephony](https://source.android.com/docs/core/connect/ims) | Public API/docs reviewed; no source revision imported | Majority Apache-2.0, with per-component exceptions; retain individual headers/notices before copying. | Public authorized Android interfaces and permission contracts are the primary integration boundary. |

Primary license/source links:

- [pagecat MIT LICENSE](https://github.com/pagecat/vowifi_gateway/blob/e3719840b93961f933aab3dac8bd2641936e2bcc/LICENSE)
- [boa-z LICENSE](https://github.com/boa-z/vowifi-go/blob/1e9c6e6adbfcd9667695149d5ecb0f71cd062f07/LICENSE)
- [gsm-sip-bridge LICENSE](https://github.com/selvakn/gsm-sip-bridge/blob/e9a653c6a3eb41780958482759c83e5b304b1191/LICENSE) and [README](https://github.com/selvakn/gsm-sip-bridge/blob/e9a653c6a3eb41780958482759c83e5b304b1191/README.md)
- [PhhIms LICENSE](https://github.com/phhusson/ims/blob/c180bdff810880d8f75f5dda70e6bcbee6991e9e/LICENSE)
- [AOSP licensing policy](https://source.android.com/docs/setup/contribute/licenses), [TelephonyManager API](https://developer.android.com/reference/android/telephony/TelephonyManager), [UICC carrier privileges](https://source.android.com/docs/core/connect/uicc)

Technical recommendation: retain existing Android domain/platform logic and use authorized Phone-as-SIM capability results to choose the next backend. A new protocol implementation is unnecessary until the audited gateway adapter boundary is defined. Complete live AKA, ePDG, IMS, each call direction and audio verification independently; no project README or container health substitutes for that evidence.

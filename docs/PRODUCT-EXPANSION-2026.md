# Product Expansion Research — 2026

## Entitlement intelligence
Treat device capability, carrier evidence and service entitlement as separate dimensions. GSMA TS.43 covers entitlement configuration for VoWiFi, VoLTE, VoNR and SMS over IP. An adapter may consume operator/platform-provided entitlement information only when documented and authorized. UNKNOWN must remain a valid state.

## 5G-ready access architecture
GSMA TS.63 explicitly covers Wi-Fi Calling in 5G SA and interworking with 4G/EPC. The product therefore models non-3GPP access behind adapters. ePDG remains an EPC-era adapter; N3IWF/TNGF research stays separate.

## Converged-call UX
For app-controlled gateway/SIP calls, evaluate stable AndroidX Core-Telecom CallsManager. This can improve system call integration and endpoint handling without pretending to control native carrier IMS.

## New product surfaces
- Entitlement card: capability vs eligibility vs activation vs evidence.
- What Changed timeline.
- SIM comparison and recommended path.
- Pre-call readiness score.
- Carrier regression warning when previously verified evidence no longer reproduces.
- Lab mode: DNS/access discovery, evidence capture, redacted export.
- Consumer mode: one readiness card and guided remediation.
- Optional app-controlled call integration with Android Telecom.
- Future 5G access adapter research; no ePDG-only architecture lock-in.

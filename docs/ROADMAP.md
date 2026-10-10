# Roadmap

## Phase 0 — Foundation
- Architecture and threat model
- Carrier evidence model
- Android diagnostic shell
- CI and unit tests
- No unsupported carrier claims

## Phase 1 — Capability Lab
- SIM/operator metadata display with privacy-safe diagnostics
- Wi-Fi quality and latency/jitter/loss measurements
- Native Wi-Fi Calling capability detection
- ePDG discovery probe without authentication
- Exportable redacted diagnostic report

## Phase 2 — Gateway PoC
- Linux gateway adapter
- SIM/USIM hardware boundary
- SWu/ePDG tunnel
- IMS registration
- Outbound/inbound voice
- Redacted traces and recovery tests

## Phase 3 — Carrier Lab
Validate one carrier at a time. Promotion requires reproducible evidence through IMS registration and real bidirectional voice.

## Phase 4 — Product
- Android call UX
- automatic best-path selection
- HD voice metrics
- multi-language UI
- safe updates
- signed releases
- privacy controls

## Non-goals
- bypassing carrier authorization or entitlement
- extracting SIM secret keys
- hidden-API hacks as a production dependency
- claiming emergency-call support before validation

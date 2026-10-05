# Evidence and diagnostic export contracts

`EvidenceLevel` remains a legacy display summary for compatibility. It must not authorize calling or establish that any other stage passed. `CarrierEvidence` records independent `EvidenceStage` observations, each with its carrier, device scope, outcome and epoch-second timestamp. Missing observations mean not tested. Failure records never verify a stage. An IMS record cannot verify SWu or ePDG, and an inbound record cannot verify outbound. `voiceVerified` requires separate successful inbound, outbound and audio observations in the requested device scope.

Scope is mandatory when querying verification. Records for another carrier/device are rejected, and an aggregate without a device scope does not verify its convenience properties. Use `EvidenceFreshnessEngine` with each observation timestamp before presenting historical evidence as current; the model retains historical successes, rather than inventing a universal expiry policy.

Quality change explanations compare only measured grades. Missing/UNKNOWN measurements cannot imply improvement or degradation.

Diagnostic redaction preserves dates, timestamps, MCC/MNC, ports, clock times and MAC addresses. It masks international phone forms, explicitly labelled national phone numbers, subscriber IDs, IPv4/IPv6 addresses and labelled authentication secrets/identities. Numeric free text is ambiguous: national phone numbers must carry a `phone`/`msisdn` label. Collect minimal structured diagnostics and never log authentication payloads or secrets in the first place; regex redaction is a fallback, not permission to collect sensitive values.

# Threat model

Protect: subscriber identity, authentication material, phone numbers, call metadata, media, carrier credentials and diagnostic exports.

Rules:
- Never persist Ki or equivalent SIM secrets.
- AKA operations remain inside SIM/USIM/modem secure boundary.
- Redact IMSI/IMPI/IMPU/MSISDN and auth challenges/responses in normal logs.
- No packet capture enabled by default.
- Diagnostic export requires explicit user action and applies redaction.
- Gateway control channel must use authenticated encryption.
- Carrier profiles are configuration, never credential stores.
- Experimental mode must clearly distinguish verified from inferred capability.

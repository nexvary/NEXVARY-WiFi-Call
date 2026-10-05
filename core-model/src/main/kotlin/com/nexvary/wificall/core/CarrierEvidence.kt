package com.nexvary.wificall.core

enum class EvidenceLevel { UNKNOWN, DISCOVERED, EPDG_REACHABLE, SWU_AUTHENTICATED, IMS_REGISTERED, OUTBOUND_VOICE_VERIFIED, INBOUND_VOICE_VERIFIED, PRODUCTION_CANDIDATE }

data class CarrierKey(val countryIso: String, val mcc: String, val mnc: String) {
 init { require(countryIso.matches(Regex("[A-Z]{2}"))); require(mcc.matches(Regex("\\d{3}"))); require(mnc.matches(Regex("\\d{2,3}"))) }
 val normalizedMnc: String get() = mnc.padStart(3, '0')
}

data class CarrierEvidence(val carrier: CarrierKey, val level: EvidenceLevel, val deviceScope: String? = null, val notes: String? = null) {
 val voiceVerified: Boolean get() = level >= EvidenceLevel.INBOUND_VOICE_VERIFIED
}

object EpdgNaming {
 fun fqdn(carrier: CarrierKey): String = "epdg.epc.mnc${carrier.normalizedMnc}.mcc${carrier.mcc}.pub.3gppnetwork.org"
}

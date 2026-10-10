package com.nexvary.wificall.core

enum class EvidenceLevel { UNKNOWN, DISCOVERED, EPDG_REACHABLE, SWU_AUTHENTICATED, IMS_REGISTERED, OUTBOUND_VOICE_VERIFIED, INBOUND_VOICE_VERIFIED, PRODUCTION_CANDIDATE }

data class CarrierKey(val countryIso: String, val mcc: String, val mnc: String) {
 init { require(countryIso.matches(Regex("[A-Z]{2}"))); require(mcc.matches(Regex("\\d{3}"))); require(mnc.matches(Regex("\\d{1,3}"))) }
 val normalizedMnc: String get() = mnc.padStart(3, '0')
}

/** Independent checks: neither their order nor a legacy summary implies another check passed. */
enum class EvidenceStage {
 EPDG_DISCOVERED, EPDG_REACHABLE, SWU_AUTHENTICATED, IMS_REGISTERED,
 OUTBOUND_VERIFIED, INBOUND_VERIFIED, AUDIO_VERIFIED
}

enum class EvidenceOutcome { VERIFIED, FAILED }

data class EvidenceObservation(
 val carrier: CarrierKey,
 val deviceScope: String,
 val checkedAtEpochSeconds: Long,
 val outcome: EvidenceOutcome = EvidenceOutcome.VERIFIED
) {
 init {
  require(deviceScope.isNotBlank())
  require(checkedAtEpochSeconds >= 0)
 }
}

data class CarrierEvidence(
 val carrier: CarrierKey,
 // Compatibility/display summary only; never use it as proof of individual stages.
 val level: EvidenceLevel = EvidenceLevel.UNKNOWN,
 val deviceScope: String? = null,
 val notes: String? = null,
 val observations: Map<EvidenceStage, EvidenceObservation> = emptyMap()
) {
 init {
  require(deviceScope == null || deviceScope.isNotBlank())
  require(observations.values.all { it.carrier == carrier && (deviceScope == null || it.deviceScope == deviceScope) })
 }

 fun isVerified(stage: EvidenceStage, forDeviceScope: String? = deviceScope): Boolean =
  observations[stage]?.let {
   it.carrier == carrier && it.outcome == EvidenceOutcome.VERIFIED &&
    forDeviceScope != null && it.deviceScope == forDeviceScope
  } ?: false

 val epdgDiscovered: Boolean get() = isVerified(EvidenceStage.EPDG_DISCOVERED)
 val epdgReachable: Boolean get() = isVerified(EvidenceStage.EPDG_REACHABLE)
 val swuAuthenticated: Boolean get() = isVerified(EvidenceStage.SWU_AUTHENTICATED)
 val imsRegistered: Boolean get() = isVerified(EvidenceStage.IMS_REGISTERED)
 val outboundVerified: Boolean get() = isVerified(EvidenceStage.OUTBOUND_VERIFIED)
 val inboundVerified: Boolean get() = isVerified(EvidenceStage.INBOUND_VERIFIED)
 val audioVerified: Boolean get() = isVerified(EvidenceStage.AUDIO_VERIFIED)
 val voiceVerified: Boolean get() = outboundVerified && inboundVerified && audioVerified
}

object EpdgNaming {
 fun fqdn(carrier: CarrierKey): String = "epdg.epc.mnc${carrier.normalizedMnc}.mcc${carrier.mcc}.pub.3gppnetwork.org"
}

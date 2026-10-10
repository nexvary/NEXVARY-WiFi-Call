package com.nexvary.wificall.core

data class SimPathCandidate(val subscription: SubscriptionRef, val evidence: EvidenceLevel, val readiness: ReadinessResult)

object SimComparator {
    fun rank(candidates: List<SimPathCandidate>): List<SimPathCandidate> = candidates.sortedWith(
        compareByDescending<SimPathCandidate> { readinessRank(it.readiness.state) }
            .thenByDescending { evidenceRank(it.evidence) }
    )
    private fun readinessRank(s: ReadinessState)=when(s){
        ReadinessState.READY_NATIVE->7; ReadinessState.READY_GATEWAY->6; ReadinessState.READY_SIP->5
        ReadinessState.DEGRADED->4; ReadinessState.RESTRICTED->3; ReadinessState.UNKNOWN->2; ReadinessState.UNSUPPORTED->1
    }
    // Directional call checks have equal weight; inbound is not a superset of outbound.
    private fun evidenceRank(e: EvidenceLevel) = when(e) {
        EvidenceLevel.UNKNOWN -> 0
        EvidenceLevel.DISCOVERED -> 1
        EvidenceLevel.EPDG_REACHABLE -> 2
        EvidenceLevel.SWU_AUTHENTICATED -> 3
        EvidenceLevel.IMS_REGISTERED -> 4
        EvidenceLevel.OUTBOUND_VOICE_VERIFIED, EvidenceLevel.INBOUND_VOICE_VERIFIED -> 5
        EvidenceLevel.PRODUCTION_CANDIDATE -> 5
    }
}

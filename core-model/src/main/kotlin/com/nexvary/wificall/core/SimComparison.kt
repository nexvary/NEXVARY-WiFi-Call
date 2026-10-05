package com.nexvary.wificall.core

data class SimPathCandidate(val subscription: SubscriptionRef, val evidence: EvidenceLevel, val readiness: ReadinessResult)

object SimComparator {
    fun rank(candidates: List<SimPathCandidate>): List<SimPathCandidate> = candidates.sortedWith(
        compareByDescending<SimPathCandidate> { readinessRank(it.readiness.state) }
            .thenByDescending { it.evidence.ordinal }
    )
    private fun readinessRank(s: ReadinessState)=when(s){
        ReadinessState.READY_NATIVE->7; ReadinessState.READY_GATEWAY->6; ReadinessState.READY_SIP->5
        ReadinessState.DEGRADED->4; ReadinessState.RESTRICTED->3; ReadinessState.UNKNOWN->2; ReadinessState.UNSUPPORTED->1
    }
}

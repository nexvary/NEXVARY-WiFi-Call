package com.nexvary.wificall.core

enum class ReadinessState {
    READY_NATIVE, READY_GATEWAY, READY_SIP, DEGRADED, RESTRICTED, UNSUPPORTED, UNKNOWN
}

enum class Blocker {
    NO_WIFI, CAPTIVE_PORTAL, INTERNET_NOT_VALIDATED, SIM_NOT_SELECTED,
    PLATFORM_RESTRICTED, CARRIER_EVIDENCE_MISSING, PATH_UNHEALTHY
}

data class NetworkSnapshot(
    val wifi: Boolean,
    val internetValidated: Boolean,
    val captivePortal: Boolean,
    val vpn: Boolean
)

data class ReadinessInput(
    val network: NetworkSnapshot,
    val simSelected: Boolean,
    val platformRestricted: Boolean,
    val nativeVerified: Boolean,
    val gatewayHealthy: Boolean,
    val sipReady: Boolean,
    val carrierEvidenceKnown: Boolean
)

data class ReadinessResult(
    val state: ReadinessState,
    val path: CallPath = CallPath.UNAVAILABLE,
    val blockers: Set<Blocker> = emptySet()
)

object ReadinessEngine {
    fun evaluate(i: ReadinessInput): ReadinessResult {
        if (!i.network.wifi) return ReadinessResult(ReadinessState.DEGRADED, blockers=setOf(Blocker.NO_WIFI))
        if (i.network.captivePortal) return ReadinessResult(ReadinessState.DEGRADED, blockers=setOf(Blocker.CAPTIVE_PORTAL))
        if (!i.network.internetValidated) return ReadinessResult(ReadinessState.DEGRADED, blockers=setOf(Blocker.INTERNET_NOT_VALIDATED))
        if (!i.simSelected) return ReadinessResult(ReadinessState.UNKNOWN, blockers=setOf(Blocker.SIM_NOT_SELECTED))
        if (i.nativeVerified) return ReadinessResult(ReadinessState.READY_NATIVE, CallPath.NATIVE_CARRIER)
        if (i.gatewayHealthy) return ReadinessResult(ReadinessState.READY_GATEWAY, CallPath.EXTERNAL_GATEWAY)
        if (i.sipReady) return ReadinessResult(ReadinessState.READY_SIP, CallPath.SIP_FALLBACK)
        if (i.platformRestricted) return ReadinessResult(ReadinessState.RESTRICTED, blockers=setOf(Blocker.PLATFORM_RESTRICTED))
        if (!i.carrierEvidenceKnown) return ReadinessResult(ReadinessState.UNKNOWN, blockers=setOf(Blocker.CARRIER_EVIDENCE_MISSING))
        return ReadinessResult(ReadinessState.UNSUPPORTED, blockers=setOf(Blocker.PATH_UNHEALTHY))
    }
}

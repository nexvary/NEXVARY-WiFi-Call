package com.nexvary.wificall.ui

import com.nexvary.wificall.core.*
import com.nexvary.wificall.platform.PhoneAsSimProbeResult

enum class AppMode { CONSUMER, LAB }
enum class AppPage { HOME, SIMS, CHANGES, DIAGNOSTICS, COMPATIBILITY, PRIVACY, ABOUT, SETTINGS, GATEWAY }
data class DashboardState(
    val readiness: ReadinessResult,
    val quality: QualityResult,
    val subscriptions: List<SubscriptionRef> = emptyList(),
    val selectedSubscriptionId: Int? = null,
    val mode: AppMode = AppMode.CONSUMER,
    val entitlement: EntitlementState = EntitlementState.UNKNOWN,
    val evidence: EvidenceLevel = EvidenceLevel.UNKNOWN,
    val changes: List<ChangeReason> = emptyList(),
    val phonePermissionRequired: Boolean = false,
    val network: NetworkSnapshot = NetworkSnapshot(false, false, false, false),
    val phoneAsSim: PhoneAsSimProbeResult? = null,
    val phoneAsSimBySubscription: Map<Int, PhoneAsSimProbeResult> = emptyMap(),
    val telephonyUnavailable: Boolean = false,
    val checking: Boolean = false
)
object DemoState {
    val value = DashboardState(
        ReadinessResult(ReadinessState.UNKNOWN, blockers = setOf(Blocker.CARRIER_EVIDENCE_MISSING)),
        QualityResult(null, QualityGrade.UNKNOWN, listOf("NO_MEASUREMENTS"))
    )
}

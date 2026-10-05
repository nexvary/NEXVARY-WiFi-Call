package com.nexvary.wificall.core

enum class ServiceKind { VOWIFI, VOLTE, VONR, SMS_OVER_IP }
enum class EntitlementState { UNKNOWN, NOT_APPLICABLE, ELIGIBLE, ACTIVATION_REQUIRED, ENABLED, DISABLED, RESTRICTED }

data class ServiceEntitlement(
    val service: ServiceKind,
    val state: EntitlementState,
    val source: String? = null,
    val checkedAtEpochSeconds: Long? = null
)

data class EntitlementSnapshot(val services: List<ServiceEntitlement>) {
    fun state(service: ServiceKind): EntitlementState =
        services.firstOrNull { it.service == service }?.state ?: EntitlementState.UNKNOWN
}

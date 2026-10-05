package com.nexvary.wificall.core

data class SubscriptionRef(
    val id: Int,
    val slotIndex: Int,
    val carrierName: String?,
    val mcc: String?,
    val mnc: String?,
    val countryIso: String?
)

sealed interface SubscriptionResult {
    data class Available(val subscriptions: List<SubscriptionRef>) : SubscriptionResult
    data object PermissionRequired : SubscriptionResult
    data object Unavailable : SubscriptionResult
}

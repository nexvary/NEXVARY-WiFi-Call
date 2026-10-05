package com.nexvary.wificall.ui

import com.nexvary.wificall.core.SubscriptionRef

/** Validates a saved choice against current subscriptions without guessing on dual-SIM devices. */
object SubscriptionSelection {
    fun resolve(subscriptions: List<SubscriptionRef>, requestedId: Int?): SubscriptionRef? =
        subscriptions.firstOrNull { it.id == requestedId } ?: subscriptions.singleOrNull()
}

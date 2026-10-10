package com.nexvary.wificall.ui

import android.content.Context
import com.nexvary.wificall.core.*
import com.nexvary.wificall.platform.AndroidNetworkProbe
import com.nexvary.wificall.platform.AndroidSubscriptionProbe
import com.nexvary.wificall.platform.PhoneAsSimCapabilityProbe

object DashboardLoader {
    fun load(context: Context, selectedSubscriptionId: Int? = null): DashboardState {
        val network = AndroidNetworkProbe(context).snapshot()
        val subsResult = AndroidSubscriptionProbe(context).active()
        val subs = when (subsResult) {
            is SubscriptionResult.Available -> subsResult.subscriptions
            else -> emptyList()
        }
        val selected = SubscriptionSelection.resolve(subs, selectedSubscriptionId)
        val permissionRestricted = subsResult is SubscriptionResult.PermissionRequired
        val input = ReadinessInput(network = network, simSelected = selected != null,
            platformRestricted = permissionRestricted, nativeVerified = false,
            gatewayHealthy = false, sipReady = false, carrierEvidenceKnown = false)
        val probe = PhoneAsSimCapabilityProbe(context)
        return DashboardState(
            readiness = ReadinessEngine.evaluate(input),
            quality = QualityEngine.evaluate(QualitySample()),
            subscriptions = subs,
            selectedSubscriptionId = selected?.id,
            phonePermissionRequired = permissionRestricted,
            telephonyUnavailable = subsResult is SubscriptionResult.Unavailable,
            network = network,
            phoneAsSim = probe.probe(selected?.id),
            phoneAsSimBySubscription = subs.associate { it.id to probe.probe(it.id) }
        )
    }
}

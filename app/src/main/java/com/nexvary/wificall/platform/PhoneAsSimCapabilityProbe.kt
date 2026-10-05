package com.nexvary.wificall.platform

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.telephony.SubscriptionManager
import android.telephony.TelephonyManager

enum class PhoneAsSimCapability {
    AVAILABLE_BY_CARRIER_PRIVILEGE,
    NO_ACTIVE_SUBSCRIPTION,
    TELEPHONY_UNAVAILABLE,
    CARRIER_PRIVILEGE_REQUIRED
}

data class PhoneAsSimProbeResult(
    val capability: PhoneAsSimCapability,
    val subscriptionId: Int? = null,
    val detail: String
)

/**
 * Non-invasive preflight only.
 *
 * This deliberately does NOT call getIccAuthentication and does not send
 * RAND/AUTN to a live USIM. It establishes whether the public carrier-
 * privilege route is available before the gateway attempts AKA.
 */
class PhoneAsSimCapabilityProbe(private val context: Context) {
    fun probe(subscriptionId: Int? = null): PhoneAsSimProbeResult {
        if (!context.packageManager.hasSystemFeature(PackageManager.FEATURE_TELEPHONY_SUBSCRIPTION)) {
            return PhoneAsSimProbeResult(
                PhoneAsSimCapability.TELEPHONY_UNAVAILABLE,
                detail = "Device does not expose telephony subscriptions."
            )
        }

        val sm = context.getSystemService(SubscriptionManager::class.java)
        val chosen = subscriptionId ?: runCatching {
            sm.activeSubscriptionInfoList?.firstOrNull()?.subscriptionId
        }.getOrNull()

        if (chosen == null || chosen == SubscriptionManager.INVALID_SUBSCRIPTION_ID) {
            return PhoneAsSimProbeResult(
                PhoneAsSimCapability.NO_ACTIVE_SUBSCRIPTION,
                detail = "No active SIM subscription is available for the AKA capability probe."
            )
        }

        val base = context.getSystemService(TelephonyManager::class.java)
        val tm = base.createForSubscriptionId(chosen)
        val hasCarrierPrivilege = runCatching {
            tm.hasCarrierPrivileges()
        }.getOrDefault(false)

        return if (hasCarrierPrivilege) {
            PhoneAsSimProbeResult(
                PhoneAsSimCapability.AVAILABLE_BY_CARRIER_PRIVILEGE,
                chosen,
                "Carrier privilege is present; an authorized ICC-auth adapter can be evaluated."
            )
        } else {
            PhoneAsSimProbeResult(
                PhoneAsSimCapability.CARRIER_PRIVILEGE_REQUIRED,
                chosen,
                "The public carrier-privilege path is unavailable. Do not attempt to bypass platform or carrier controls."
            )
        }
    }
}

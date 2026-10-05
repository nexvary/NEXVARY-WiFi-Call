package com.nexvary.wificall.platform

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.telephony.SubscriptionManager
import android.telephony.TelephonyManager
import androidx.core.content.ContextCompat

enum class PhoneAsSimCapability {
    AVAILABLE_BY_CARRIER_PRIVILEGE,
    NO_ACTIVE_SUBSCRIPTION,
    TELEPHONY_UNAVAILABLE,
    CARRIER_PRIVILEGE_REQUIRED,
    PERMISSION_REQUIRED,
    UNSUPPORTED,
    SIM_NOT_SELECTED
}

data class PhoneAsSimProbeResult(
    val capability: PhoneAsSimCapability,
    val subscriptionId: Int? = null,
    /** Lab evidence only; consumer text must come from translated resources. */
    val detail: String
)

/**
 * Public API capability preflight, never a live AKA verification.
 * No getIccAuthentication call, RAND/AUTN challenge, Ki extraction, or secret storage.
 * Carrier privileges allow evaluating a future authorized adapter, but do not prove
 * that a USIM accepts EAP-AKA or that SWu/IMS/calling works.
 */
class PhoneAsSimCapabilityProbe(private val context: Context) {
    fun probe(subscriptionId: Int? = null): PhoneAsSimProbeResult {
        fun result(capability: PhoneAsSimCapability, detail: String, id: Int? = subscriptionId) =
            PhoneAsSimProbeResult(capability, id, detail)
        if (!context.packageManager.hasSystemFeature(PackageManager.FEATURE_TELEPHONY_SUBSCRIPTION)) {
            return result(PhoneAsSimCapability.TELEPHONY_UNAVAILABLE, "Telephony subscription feature is absent.")
        }
        val sm = context.getSystemService(SubscriptionManager::class.java)
            ?: return result(PhoneAsSimCapability.TELEPHONY_UNAVAILABLE, "Subscription service is unavailable.")
        val base = context.getSystemService(TelephonyManager::class.java)
            ?: return result(PhoneAsSimCapability.TELEPHONY_UNAVAILABLE, "Telephony service is unavailable.")
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED) {
            return result(PhoneAsSimCapability.PERMISSION_REQUIRED, "READ_PHONE_STATE is not granted.")
        }
        return try {
            val subscriptions = sm.activeSubscriptionInfoList.orEmpty()
            if (subscriptions.isEmpty()) {
                result(PhoneAsSimCapability.NO_ACTIVE_SUBSCRIPTION, "No active subscription was reported.", null)
            } else {
                val chosen = subscriptions.firstOrNull { it.subscriptionId == subscriptionId }
                    ?: if (subscriptionId == null) subscriptions.singleOrNull() else null
                if (chosen == null) {
                    result(PhoneAsSimCapability.SIM_NOT_SELECTED, "Select an active subscription before capability preflight.", null)
                } else {
                    val tm = base.createForSubscriptionId(chosen.subscriptionId)
                    if (tm.hasCarrierPrivileges()) {
                        result(PhoneAsSimCapability.AVAILABLE_BY_CARRIER_PRIVILEGE,
                            "hasCarrierPrivileges=true; live USIM EAP-AKA is not tested.", chosen.subscriptionId)
                    } else {
                        result(PhoneAsSimCapability.CARRIER_PRIVILEGE_REQUIRED,
                            "hasCarrierPrivileges=false; public ICC authentication requires carrier authorization. No bypass attempted.", chosen.subscriptionId)
                    }
                }
            }
        } catch (_: SecurityException) {
            result(PhoneAsSimCapability.PERMISSION_REQUIRED, "Android denied the subscription capability query.")
        } catch (_: UnsupportedOperationException) {
            result(PhoneAsSimCapability.UNSUPPORTED, "Public subscription capability query is unsupported.")
        } catch (_: RuntimeException) {
            result(PhoneAsSimCapability.TELEPHONY_UNAVAILABLE, "Telephony capability query is temporarily unavailable.")
        }
    }
}

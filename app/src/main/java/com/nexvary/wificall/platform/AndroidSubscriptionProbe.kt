package com.nexvary.wificall.platform

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.telephony.SubscriptionManager
import androidx.core.content.ContextCompat
import com.nexvary.wificall.core.SubscriptionRef
import com.nexvary.wificall.core.SubscriptionResult

class AndroidSubscriptionProbe(private val context: Context) {
    private val sm = context.getSystemService(SubscriptionManager::class.java)

    fun active(): SubscriptionResult {
        if (!context.packageManager.hasSystemFeature(PackageManager.FEATURE_TELEPHONY_SUBSCRIPTION) || sm == null) {
            return SubscriptionResult.Unavailable
        }
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED) {
            return SubscriptionResult.PermissionRequired
        }
        return try {
            val list = sm.activeSubscriptionInfoList.orEmpty().map {
                SubscriptionRef(
                    id = it.subscriptionId,
                    slotIndex = it.simSlotIndex,
                    carrierName = it.carrierName?.toString(),
                    mcc = it.mccString,
                    mnc = it.mncString,
                    countryIso = it.countryIso?.uppercase()
                )
            }
            SubscriptionResult.Available(list)
        } catch (_: SecurityException) {
            SubscriptionResult.PermissionRequired
        } catch (_: RuntimeException) {
            SubscriptionResult.Unavailable
        }
    }
}

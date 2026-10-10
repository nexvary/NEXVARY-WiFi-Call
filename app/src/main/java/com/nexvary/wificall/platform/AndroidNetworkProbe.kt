package com.nexvary.wificall.platform

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import com.nexvary.wificall.core.NetworkSnapshot

/** Snapshot reads are refreshed by the activity's lifecycle-scoped network callback. */
class AndroidNetworkProbe(context: Context) {
    private val cm = context.getSystemService(ConnectivityManager::class.java)

    fun snapshot(): NetworkSnapshot {
        val unavailable = NetworkSnapshot(false, false, false, false)
        return try {
            val network = cm?.activeNetwork ?: return unavailable
            val caps = cm.getNetworkCapabilities(network) ?: return unavailable
            NetworkSnapshot(
                wifi = caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI),
                internetValidated = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED),
                captivePortal = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_CAPTIVE_PORTAL),
                vpn = caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
            )
        } catch (_: SecurityException) {
            unavailable
        } catch (_: RuntimeException) {
            unavailable
        }
    }
}

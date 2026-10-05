package com.nexvary.wificall.platform

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import com.nexvary.wificall.core.NetworkSnapshot

class AndroidNetworkProbe(context: Context) {
    private val cm = context.getSystemService(ConnectivityManager::class.java)

    fun snapshot(): NetworkSnapshot {
        val network = cm.activeNetwork ?: return NetworkSnapshot(false, false, false, false)
        val caps = cm.getNetworkCapabilities(network) ?: return NetworkSnapshot(false, false, false, false)
        return NetworkSnapshot(
            wifi = caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI),
            internetValidated = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED),
            captivePortal = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_CAPTIVE_PORTAL),
            vpn = caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
        )
    }
}

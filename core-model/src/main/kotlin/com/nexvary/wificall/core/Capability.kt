package com.nexvary.wificall.core

enum class CallPath { NATIVE_CARRIER, EXTERNAL_GATEWAY, SIP_FALLBACK, UNAVAILABLE }

data class CarrierIdentity(val mcc: String, val mnc: String) {
    init {
        require(mcc.matches(Regex("\\d{3}")))
        require(mnc.matches(Regex("\\d{2,3}")))
    }
}

data class CapabilitySnapshot(
    val carrier: CarrierIdentity?,
    val wifiConnected: Boolean,
    val carrierPrivileges: Boolean,
    val nativeWfcAdvertised: Boolean,
    val authorizedGatewayConfigured: Boolean,
    val sipConfigured: Boolean
) {
    fun preferredPath(): CallPath = when {
        wifiConnected && carrierPrivileges && nativeWfcAdvertised -> CallPath.NATIVE_CARRIER
        wifiConnected && authorizedGatewayConfigured -> CallPath.EXTERNAL_GATEWAY
        wifiConnected && sipConfigured -> CallPath.SIP_FALLBACK
        else -> CallPath.UNAVAILABLE
    }
}

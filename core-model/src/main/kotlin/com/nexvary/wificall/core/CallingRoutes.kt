package com.nexvary.wificall.core

enum class CallingRoute { CARRIER_WIFI, EXTERNAL_USIM, CELLULAR_VOICE, SIP_INTERNAL }
enum class RouteAvailability { AVAILABLE, NEEDS_SETUP, NOT_VERIFIED, UNSUPPORTED_BY_EVIDENCE, OFFLINE }
data class RouteEvidence(
    val configured: Boolean = false,
    val online: Boolean = false,
    val authenticated: Boolean = false,
    val mediaVerified: Boolean = false,
    val hardwareSupported: Boolean? = null,
    val operatorAuthorized: Boolean = false,
    val akaVerified: Boolean = false,
    val ipsecVerified: Boolean = false,
    val imsRegistered: Boolean = false,
    val inboundVerified: Boolean = false,
    val outboundVerified: Boolean = false,
    val voiceModemVerified: Boolean = false
)
object CallingRouteEngine {
    fun evaluate(route: CallingRoute, e: RouteEvidence): RouteAvailability {
        if (e.hardwareSupported == false) return RouteAvailability.UNSUPPORTED_BY_EVIDENCE
        if (!e.configured) return RouteAvailability.NEEDS_SETUP
        if (!e.online) return RouteAvailability.OFFLINE
        val verified = e.authenticated && e.mediaVerified && e.inboundVerified && e.outboundVerified && when (route) {
            CallingRoute.CARRIER_WIFI, CallingRoute.EXTERNAL_USIM -> e.operatorAuthorized && e.akaVerified && e.ipsecVerified && e.imsRegistered
            CallingRoute.CELLULAR_VOICE -> e.voiceModemVerified
            CallingRoute.SIP_INTERNAL -> true
        }
        return if (verified) RouteAvailability.AVAILABLE else RouteAvailability.NOT_VERIFIED
    }
}
/** PBX-local extensions only; short emergency numbers are deliberately never dialled. */
object InternalDialPolicy {
    fun validExtension(value: String): Boolean = value.matches(Regex("[1-9][0-9]{3,5}")) &&
        value !in setOf("100", "101", "102", "112", "122", "123", "180", "911", "999")
    fun validHost(value: String): Boolean = value.length in 1..253 &&
        value.matches(Regex("[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?")) && !value.contains("..")
    fun validPort(value: Int) = value in 1..65535
}

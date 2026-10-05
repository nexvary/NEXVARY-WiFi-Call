package com.nexvary.wificall.core

enum class ChangeReason { WIFI_LOST, WIFI_GAINED, VALIDATION_LOST, VALIDATION_GAINED, CAPTIVE_PORTAL_APPEARED, CAPTIVE_PORTAL_CLEARED, VPN_ENABLED, VPN_DISABLED, DNS_CHANGED, QUALITY_DEGRADED, QUALITY_IMPROVED }

data class ChangeExplanation(val reasons: List<ChangeReason>)

object ChangeExplainer {
    fun compare(before: NetworkContext, after: NetworkContext, beforeQuality: QualityGrade? = null, afterQuality: QualityGrade? = null): ChangeExplanation {
        val r=mutableListOf<ChangeReason>()
        if(before.wifi&&!after.wifi) r+=ChangeReason.WIFI_LOST
        if(!before.wifi&&after.wifi) r+=ChangeReason.WIFI_GAINED
        if(before.validated&&!after.validated) r+=ChangeReason.VALIDATION_LOST
        if(!before.validated&&after.validated) r+=ChangeReason.VALIDATION_GAINED
        if(!before.captivePortal&&after.captivePortal) r+=ChangeReason.CAPTIVE_PORTAL_APPEARED
        if(before.captivePortal&&!after.captivePortal) r+=ChangeReason.CAPTIVE_PORTAL_CLEARED
        if(!before.vpn&&after.vpn) r+=ChangeReason.VPN_ENABLED
        if(before.vpn&&!after.vpn) r+=ChangeReason.VPN_DISABLED
        if(before.dnsServerCount!=after.dnsServerCount) r+=ChangeReason.DNS_CHANGED
        if(beforeQuality!=null&&afterQuality!=null) {
            if(afterQuality.ordinal>beforeQuality.ordinal) r+=ChangeReason.QUALITY_DEGRADED
            if(afterQuality.ordinal<beforeQuality.ordinal) r+=ChangeReason.QUALITY_IMPROVED
        }
        return ChangeExplanation(r)
    }
}

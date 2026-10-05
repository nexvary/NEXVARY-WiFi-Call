package com.nexvary.wificall.core

data class Remediation(val blocker:Blocker,val actionKey:String,val priority:Int)
object RemediationEngine { fun forBlockers(b:Set<Blocker>)=b.map{Remediation(it,when(it){Blocker.NO_WIFI->"CONNECT_WIFI";Blocker.CAPTIVE_PORTAL->"SIGN_IN_WIFI";Blocker.INTERNET_NOT_VALIDATED->"CHECK_INTERNET";Blocker.SIM_NOT_SELECTED->"SELECT_SIM";Blocker.PLATFORM_RESTRICTED->"OPEN_SYSTEM_WIFI_CALLING";Blocker.CARRIER_EVIDENCE_MISSING->"RUN_COMPATIBILITY_CHECK";Blocker.PATH_UNHEALTHY->"RETRY_OR_CHANGE_NETWORK"},when(it){Blocker.NO_WIFI,Blocker.CAPTIVE_PORTAL->100;Blocker.INTERNET_NOT_VALIDATED->90;else->50})}.sortedByDescending{it.priority} }

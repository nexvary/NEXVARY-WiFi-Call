package com.nexvary.wificall.core

enum class EvidenceFreshness { FRESH, AGING, EXPIRED, UNDATED }
object EvidenceFreshnessEngine { fun evaluate(checkedAtEpochSeconds:Long?,nowEpochSeconds:Long):EvidenceFreshness { if(checkedAtEpochSeconds==null)return EvidenceFreshness.UNDATED; val age=(nowEpochSeconds-checkedAtEpochSeconds).coerceAtLeast(0); return when { age<=30L*86400->EvidenceFreshness.FRESH; age<=90L*86400->EvidenceFreshness.AGING; else->EvidenceFreshness.EXPIRED } } }

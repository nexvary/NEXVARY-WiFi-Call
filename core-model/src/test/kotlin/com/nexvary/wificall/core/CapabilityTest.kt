package com.nexvary.wificall.core

import kotlin.test.*

class CapabilityTest {
    @Test fun nativePreferred() {
        assertEquals(CallPath.NATIVE_CARRIER, CapabilitySnapshot(CarrierIdentity("234","15"), true, true, true, true, true).preferredPath())
    }
    @Test fun gatewayFallback() {
        assertEquals(CallPath.EXTERNAL_GATEWAY, CapabilitySnapshot(null, true, false, false, true, true).preferredPath())
    }
    @Test fun offlineUnavailable() {
        assertEquals(CallPath.UNAVAILABLE, CapabilitySnapshot(null, false, false, false, true, true).preferredPath())
    }
    @Test fun validatesPlmn() {
        assertFailsWith<IllegalArgumentException> { CarrierIdentity("20","1") }
    }
}

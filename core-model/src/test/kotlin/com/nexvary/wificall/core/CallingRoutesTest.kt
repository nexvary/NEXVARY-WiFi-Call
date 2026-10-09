package com.nexvary.wificall.core
import kotlin.test.*
class CallingRoutesTest {
    @Test fun registrationDoesNotProveAudio() {
        assertEquals(RouteAvailability.NOT_VERIFIED, CallingRouteEngine.evaluate(CallingRoute.SIP_INTERNAL, RouteEvidence(true, true, true)))
        assertEquals(RouteAvailability.AVAILABLE, CallingRouteEngine.evaluate(CallingRoute.SIP_INTERNAL, RouteEvidence(true, true, true, true, inboundVerified = true, outboundVerified = true)))
    }
    @Test fun dnsAndSimAccessDoNotProveCarrierCalls() {
        assertEquals(RouteAvailability.NOT_VERIFIED, CallingRouteEngine.evaluate(CallingRoute.CARRIER_WIFI, RouteEvidence(true, true, true, true)))
    }
    @Test fun eachCarrierStageIsRequired() {
        val complete = RouteEvidence(true, true, true, true, operatorAuthorized = true, akaVerified = true,
            ipsecVerified = true, imsRegistered = true, inboundVerified = true, outboundVerified = true)
        assertEquals(RouteAvailability.AVAILABLE, CallingRouteEngine.evaluate(CallingRoute.CARRIER_WIFI, complete))
        listOf(complete.copy(akaVerified = false), complete.copy(ipsecVerified = false),
            complete.copy(imsRegistered = false), complete.copy(operatorAuthorized = false),
            complete.copy(inboundVerified = false)).forEach { e ->
            assertEquals(RouteAvailability.NOT_VERIFIED, CallingRouteEngine.evaluate(CallingRoute.CARRIER_WIFI, e))
        }
        assertEquals(RouteAvailability.NOT_VERIFIED, CallingRouteEngine.evaluate(CallingRoute.CELLULAR_VOICE, complete))
        assertEquals(RouteAvailability.AVAILABLE, CallingRouteEngine.evaluate(CallingRoute.CELLULAR_VOICE, complete.copy(voiceModemVerified = true)))
    }
    @Test fun offlineAndExplicitUnsupportedAreDistinct() {
        assertEquals(RouteAvailability.OFFLINE, CallingRouteEngine.evaluate(CallingRoute.CELLULAR_VOICE, RouteEvidence(configured = true)))
        assertEquals(RouteAvailability.UNSUPPORTED_BY_EVIDENCE, CallingRouteEngine.evaluate(CallingRoute.EXTERNAL_USIM, RouteEvidence(hardwareSupported = false)))
    }
    @Test fun diallerRejectsExternalNumbersUrisAndInjection() {
        listOf("+201012345678", "112", "100@evil.example", "100\r\nVia:", "*100#", "000", "1234567").forEach { value ->
            assertFalse(InternalDialPolicy.validExtension(value))
        }
        assertTrue(InternalDialPolicy.validExtension("1001"))
        assertFalse(InternalDialPolicy.validHost("example.org;transport=udp"))
        assertFalse(InternalDialPolicy.validHost("evil..org"))
    }
}

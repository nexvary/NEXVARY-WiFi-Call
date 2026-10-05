package com.nexvary.wificall.platform.gateway

import com.nexvary.wificall.platform.PhoneAsSimCapability
import org.junit.Assert.*
import org.junit.Test

class GatewayContractTest {
    @Test fun httpsAddressesNormalizeWithoutChangingTheirOrigin() {
        assertEquals("https://example.org", GatewayAddress.normalize(" https://example.org/ "))
        assertEquals("https://example.org:8443", GatewayAddress.normalize("https://example.org:8443"))
    }

    @Test fun rejectsCleartextCredentialsAmbiguousPathsAndInjectedMetadata() {
        listOf("http://127.0.0.1:8787", "http://example.org", "https://user:pass@example.org", "https://example.org/path",
            "https://example.org?token=a", "https://example.org/#fragment", "https://example.org:0", "https://example.org:65536",
            "//example.org", "https://", "https://example.org/../", "https://example.org\\@evil.org")
            .forEach { assertNull(it, GatewayAddress.normalize(it)) }
    }

    @Test fun reportBoundsRejectInventedSlotsAndInvalidSimCounts() {
        fun report(count: Int, slot: Int?) = GatewayReport(count, slot, GatewayNetwork.WIFI,
            PhoneAsSimCapability.CARRIER_PRIVILEGE_REQUIRED, "0.3.0-alpha01", 35)
        assertTrue(report(2, 1).isValid())
        assertTrue(report(0, null).isValid())
        assertFalse(report(0, 0).isValid())
        assertFalse(report(9, null).isValid())
        assertFalse(report(2, -1).isValid())
        assertFalse(report(2, 8).isValid())
    }

    @Test fun urlSafePairingCodesAcceptUnderscoresAndRejectSmallGuessableCodes() {
        assertTrue(GatewayValidation.pairCode("abcdef0123456789_ABCDEF-0123456789"))
        assertFalse(GatewayValidation.pairCode("123456"))
        assertFalse(GatewayValidation.pairCode("abcdef0123456789/ABCDEF0123456789"))
        assertFalse(GatewayValidation.token("a".repeat(129)))
        assertFalse(GatewayValidation.token("a".repeat(31)))
        assertTrue(GatewayValidation.token("a".repeat(43)))
    }

    @Test fun credentialToStringDoesNotRevealPairingSecrets() {
        val credentials = GatewayCredentials("https://example.org", "device-123", "secret-bearer-123456")
        assertFalse(credentials.toString().contains(credentials.token))
        assertFalse(credentials.toString().contains(credentials.deviceId))
    }
}

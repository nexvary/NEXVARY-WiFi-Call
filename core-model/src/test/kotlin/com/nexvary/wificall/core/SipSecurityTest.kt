package com.nexvary.wificall.core

import kotlin.test.*

class SipSecurityTest {
    private val now = 1_800_000_000L
    private val password = "MDEyMzQ1Njc4OWFiY2RlZg=="
    private fun parse(endpoint: String = "turns:relay.example.org:5349?transport=tcp", username: String = "${now + 300}:device-1", secret: String = password) =
        SecureTurnSettings.parse(endpoint, username, secret, now)

    @Test fun tlsRelayWithShortLivedCredentialsIsAcceptedWithoutSecretLogging() {
        val settings = parse()
        assertEquals("relay.example.org:5349", settings.sdkServer)
        assertEquals(now + 300, settings.expiresAtSeconds)
        assertTrue(settings.isFresh(now + 299))
        assertFalse(settings.isFresh(now + 300))
        assertFalse(settings.toString().contains(password))
        assertFalse(settings.toString().contains(settings.username))
        assertEquals(5349, parse("turns:127.0.0.1:5349").port)
    }

    @Test fun insecureTransportsUriCredentialsPathsAndInvalidPortsAreRejected() {
        listOf("turn:relay.example.org:3478", "turns:relay.example.org:5349?transport=udp",
            "turns://user:pass@relay.example.org:5349", "turns:relay.example.org:5349/path",
            "turns:relay.example.org:0", "turns:relay.example.org:65536",
            "turns:relay..example.org:5349", "turns:-relay.example.org:5349",
            "turns:relay.example.org:5349\r\n").forEach { endpoint ->
            assertFailsWith<IllegalArgumentException>(endpoint) { parse(endpoint) }
        }
    }

    @Test fun expiredLongLivedPermanentAndMalformedCredentialsAreRejected() {
        listOf("$now:device", "${now - 1}:device", "${now + 3601}:device", "device",
            "${now + 300}:device\n", "9999999999999999999:device").forEach { username ->
            assertFailsWith<IllegalArgumentException> { parse(username = username) }
        }
        listOf("short", "$password\n", "password with spaces", "").forEach { secret ->
            assertFailsWith<IllegalArgumentException> { parse(secret = secret) }
        }
        assertEquals(now + 3600, parse(username = "${now + 3600}:device").expiresAtSeconds)
    }

    @Test fun dtmfAcceptsOnlyAsciiDigitsStarAndHash() {
        "0123456789*#".forEach { assertTrue(DtmfPolicy.validDigit(it)) }
        listOf('A', 'd', '+', ' ', '\n', '\u0000', '١', '５').forEach { assertFalse(DtmfPolicy.validDigit(it)) }
    }
}

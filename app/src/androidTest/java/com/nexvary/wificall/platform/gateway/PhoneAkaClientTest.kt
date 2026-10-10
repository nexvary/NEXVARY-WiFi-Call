package com.nexvary.wificall.platform.gateway

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

class PhoneAkaClientTest {
    private class Fixture(url: URL, val reply: String, val status: Int = 200) : HttpURLConnection(url) {
        val sent = ByteArrayOutputStream()
        override fun connect() { }
        override fun disconnect() { }
        override fun usingProxy() = false
        override fun getOutputStream() = sent
        override fun getInputStream() = ByteArrayInputStream(reply.toByteArray())
        override fun getResponseCode() = status
    }
    private val credentials = GatewayCredentials("https://gateway.example.org", "test-device", "0123456789_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef")
    private val sessionId = "session_012345678901234567890123456789"
    private val challengeId = "challenge_012345678901234567890123456789"
    private fun now() = System.currentTimeMillis() / 1000
    private fun challenge(expiry: Long = now() + 25, slot: Int = 1) = JSONObject().put("challenge_id", challengeId)
        .put("session_id", sessionId).put("selected_slot", slot)
        .put("rand", "00".repeat(16)).put("autn", "11".repeat(16)).put("expires_at", expiry.toInt())

    @Test fun sessionPollAndResponseUseAuthorizedExactHttpsContract() {
        val requests = mutableListOf<Fixture>()
        val client = PhoneAkaClient { url ->
            val body = when (url.path.substringAfterLast('/')) {
                "session" -> JSONObject().put("session_id", sessionId).put("selected_slot", 1).put("expires_at", (now() + 290).toInt()).toString()
                "poll" -> JSONObject().put("challenge", challenge()).toString()
                else -> "{\"ok\":true}"
            }
            Fixture(url, body).also { requests.add(it) }
        }
        val session = (client.start(credentials, 1) as GatewayResult.Success).value
        val pending = (client.poll(credentials, session) as GatewayResult.Success).value!!
        val response = PhoneAkaCodec.parse(byteArrayOf(0xdb.toByte(), 8) + ByteArray(8) { 1 } + byteArrayOf(16) +
            ByteArray(16) { 2 } + byteArrayOf(16) + ByteArray(16) { 3 })
        try { assertTrue(client.submit(credentials, session, pending, response) is GatewayResult.Success) }
        finally { response.destroy() }
        val result = requests[2]
        val json = JSONObject(result.sent.toString("UTF-8"))
        assertEquals(setOf("session_id", "challenge_id", "state", "payload"), json.keys().asSequence().toSet())
        assertEquals(sessionId, json.getString("session_id")); assertEquals(challengeId, json.getString("challenge_id"))
        assertEquals("SUCCESS", json.getString("state"))
        assertTrue(PhoneAkaCodec.parse(android.util.Base64.decode(json.getString("payload"), android.util.Base64.NO_WRAP)) is PhoneAkaResult.Success)
        requests.forEach {
            assertEquals("https", it.url.protocol)
            assertFalse(it.instanceFollowRedirects)
            assertEquals("Bearer ${credentials.token}", it.getRequestProperty("Authorization"))
            assertEquals(10000, it.readTimeout)
        }
    }

    @Test fun expiredOverscopedOrMalformedChallengesAreRejectedBeforeSimApi() {
        val session = PhoneAkaSession(sessionId, now() + 290, 1)
        val values = listOf(challenge(now() - 1), challenge(now() + 60), challenge(slot = 0),
            challenge().put("rand", "short"), challenge().put("expires_at", "123"),
            challenge().put("extra", true), challenge().also { it.remove("session_id") },
            challenge().also { it.remove("selected_slot") })
        values.forEach { value ->
            val client = PhoneAkaClient { url -> Fixture(url, JSONObject().put("challenge", value).toString()) }
            assertEquals(GatewayResult.Failure(GatewayError.INVALID_RESPONSE), client.poll(credentials, session))
        }
        val empty = PhoneAkaClient { url -> Fixture(url, "{\"challenge\":null}") }
        assertNull((empty.poll(credentials, session) as GatewayResult.Success).value)
    }

    @Test fun strictSessionResponseAndLocalExpiryPreventUnscopedOrLateRequests() {
        val good = JSONObject().put("session_id", sessionId).put("selected_slot", 1).put("expires_at", (now() + 290).toInt())
        val cases = listOf(JSONObject(good.toString()).put("selected_slot", 0),
            JSONObject(good.toString()).put("unknown", true),
            JSONObject(good.toString()).put("session_id", "short"),
            JSONObject(good.toString()).also { it.remove("selected_slot") })
        cases.forEach { json ->
            val client = PhoneAkaClient { url -> Fixture(url, json.toString()) }
            assertEquals(GatewayResult.Failure(GatewayError.INVALID_RESPONSE), client.start(credentials, 1))
        }
        var requests = 0
        val client = PhoneAkaClient { url -> requests++; Fixture(url, "{\"ok\":true}") }
        val expired = PhoneAkaSession(sessionId, now() - 1, 1)
        assertEquals(GatewayResult.Failure(GatewayError.INVALID_REPORT), client.poll(credentials, expired))
        val current = PhoneAkaSession(sessionId, now() + 290, 1)
        val oldChallenge = PhoneAkaChallenge(challengeId, "00".repeat(16), "11".repeat(16), now() - 1)
        assertEquals(GatewayResult.Failure(GatewayError.INVALID_REPORT), client.submit(credentials, current,
            oldChallenge, PhoneAkaResult.Failure(PhoneAkaError.NULL_RESPONSE)))
        assertEquals(0, requests)
    }

    @Test fun errorResponsesContainNoPayloadAndRevocationStopsPolling() {
        lateinit var sent: Fixture
        val session = PhoneAkaSession(sessionId, now() + 290, 1)
        val challenge = PhoneAkaChallenge(challengeId, "00".repeat(16), "11".repeat(16), now() + 25)
        val client = PhoneAkaClient { url -> Fixture(url, "{\"ok\":true}").also { sent = it } }
        assertTrue(client.submit(credentials, session, challenge,
            PhoneAkaResult.Failure(PhoneAkaError.CARRIER_PRIVILEGE_REQUIRED)) is GatewayResult.Success)
        val json = JSONObject(sent.sent.toString("UTF-8"))
        assertEquals("CARRIER_PRIVILEGE_REQUIRED", json.getString("state"))
        assertTrue(json.isNull("payload"))
        val revoked = PhoneAkaClient { url -> Fixture(url, "{}", 401) }
        assertEquals(GatewayResult.Failure(GatewayError.UNAUTHORIZED), revoked.poll(credentials, session))
        val falseAck = PhoneAkaClient { url -> Fixture(url, "{\"ok\":false}") }
        assertEquals(GatewayResult.Failure(GatewayError.INVALID_RESPONSE), falseAck.stop(credentials, session))
    }
}

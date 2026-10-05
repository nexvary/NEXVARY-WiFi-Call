package com.nexvary.wificall.platform.gateway

import com.nexvary.wificall.platform.PhoneAsSimCapability
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

/** Uses the real client serialization and response parser, replacing only transport. No TLS exceptions. */
class GatewayClientTest {
    private class Fixture(url: URL, private val status: Int, private val response: String) : HttpURLConnection(url) {
        val sent = ByteArrayOutputStream()
        var closed = false
        override fun connect() { }
        override fun disconnect() { closed = true }
        override fun usingProxy() = false
        override fun getOutputStream() = sent
        override fun getInputStream() = ByteArrayInputStream(response.toByteArray(Charsets.UTF_8))
        override fun getResponseCode() = status
    }
    private val secret = "0123456789_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    private val credentials = GatewayCredentials("https://gateway.example.org", "device-123", secret)
    private val report = GatewayReport(2, 1, GatewayNetwork.WIFI,
        PhoneAsSimCapability.CARRIER_PRIVILEGE_REQUIRED, "0.3.0-alpha01", 35)

    @Test fun pairAndReportUseExactJsonContractAndBearerHeader() {
        val requests = mutableListOf<Fixture>()
        val client = GatewayClient { url ->
            Fixture(url, 200, if (url.path.endsWith("pair"))
                JSONObject().put("device_id", credentials.deviceId).put("token", secret).toString()
                else "{\"ok\":true}").also { requests.add(it) }
        }
        val code = "0123456789_ABCDEFGHIJKLMNOPQRSTUV"
        val paired = client.pair("https://gateway.example.org/", code)
        assertTrue(paired is GatewayResult.Success)
        assertEquals(secret, (paired as GatewayResult.Success).value.token)
        assertTrue(client.report(paired.value, report) is GatewayResult.Success)
        val pair = requests[0]
        assertEquals("https://gateway.example.org/api/phone/pair", pair.url.toString())
        assertEquals("POST", pair.requestMethod)
        assertEquals("application/json; charset=utf-8", pair.getRequestProperty("Content-Type"))
        assertNull(pair.getRequestProperty("Authorization"))
        val pairBody = JSONObject(pair.sent.toString("UTF-8"))
        assertEquals(1, pairBody.length())
        assertEquals(code, pairBody.getString("code"))
        val sent = requests[1]
        assertEquals("Bearer $secret", sent.getRequestProperty("Authorization"))
        val json = JSONObject(sent.sent.toString("UTF-8"))
        assertEquals(setOf("schema_version", "sim_count", "selected_slot", "network", "phone_as_sim", "app_version", "android_api"), json.keys().asSequence().toSet())
        assertEquals(1, json.getInt("schema_version"))
        assertEquals(2, json.getInt("sim_count"))
        assertEquals(1, json.getInt("selected_slot"))
        assertEquals("WIFI", json.getString("network"))
        assertEquals("CARRIER_PRIVILEGE_REQUIRED", json.getString("phone_as_sim"))
        assertEquals("0.3.0-alpha01", json.getString("app_version"))
        assertEquals(35, json.getInt("android_api"))
        requests.forEach {
            assertFalse(it.instanceFollowRedirects)
            assertEquals(10_000, it.connectTimeout)
            assertEquals(10_000, it.readTimeout)
            assertTrue(it.closed)
        }
    }

    @Test fun uncheckedCapabilityAndNoSelectionRemainUnknownAndNull() {
        lateinit var sent: Fixture
        val client = GatewayClient { url -> Fixture(url, 200, "{\"ok\":true}").also { sent = it } }
        assertTrue(client.report(credentials, GatewayReport(0, null, GatewayNetwork.UNKNOWN, null, "0.3.0-alpha01", 35)) is GatewayResult.Success)
        val json = JSONObject(sent.sent.toString("UTF-8"))
        assertTrue(json.isNull("selected_slot"))
        assertEquals("UNKNOWN", json.getString("phone_as_sim"))
    }

    @Test fun falseMalformedOrStringAcknowledgementsNeverCountAsSuccess() {
        listOf("{\"ok\":false}", "not-json", "{\"ok\":\"true\"}", "{}").forEach { body ->
            val client = GatewayClient { url -> Fixture(url, 200, body) }
            assertEquals(GatewayResult.Failure(GatewayError.INVALID_RESPONSE), client.report(credentials, report))
        }
    }

    @Test fun redirectsUnauthorizedAndOversizeResponsesFailWithoutFollowing() {
        listOf(302 to GatewayError.REJECTED, 401 to GatewayError.UNAUTHORIZED, 403 to GatewayError.REJECTED).forEach { (status, error) ->
            lateinit var request: Fixture
            val client = GatewayClient { url -> Fixture(url, status, "{\"ok\":true}").also { request = it } }
            assertEquals(GatewayResult.Failure(error), client.disconnect(credentials))
            assertFalse(request.instanceFollowRedirects)
            assertEquals("/api/phone/disconnect", request.url.path)
        }
        val oversized = GatewayClient { url -> Fixture(url, 200, " ".repeat(8193)) }
        assertEquals(GatewayResult.Failure(GatewayError.INVALID_RESPONSE), oversized.report(credentials, report))
    }
}

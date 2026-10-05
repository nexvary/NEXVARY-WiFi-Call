package com.nexvary.wificall.platform.gateway

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class PairingQrParserTest {
    private val code = "abcdefghijklmnopqrstuvwxyz_0123456789ABCDEFG"
    private fun payload(url: Any = "https://3.65.234.184:8443", version: Any = 1, token: Any = code) =
        JSONObject().put("type", "nexvary-pairing").put("version", version).put("url", url).put("code", token).toString()

    @Test fun acceptsExactServerPayloadWithoutAuthorizingARequest() {
        val candidate = PairingQrParser.parse(payload())!!
        assertEquals("https://3.65.234.184:8443", candidate.url)
        assertEquals(code, candidate.code)
        assertFalse(candidate.toString().contains(code))
    }

    @Test fun rejectsUnknownDuplicateMalformedOrWronglyTypedFields() {
        val raw = payload()
        listOf(raw.dropLast(1) + ",\"extra\":true}", raw.dropLast(1) + ",\"version\":1}",
            raw + "trailing", raw.replace('"', '\''), payload(version = "1"), payload(version = true),
            payload(version = 1.5), payload(version = 2), payload(url = 123), payload(token = true),
            payload(token = "short"), raw.replace("nexvary-pairing", "other"), " ".repeat(4097),
            "{}", "null", "[]").forEach { assertNull(it.take(40), PairingQrParser.parse(it)) }
        assertNull(PairingQrParser.parse(null))
    }

    @Test fun rejectsHttpAndUnsafeHttpsOrigins() {
        listOf("http://3.65.234.184:8443", "https://user:secret@example.org", "https://example.org/api",
            "https://example.org?code=secret", "https://example.org#fragment", "https://example.org:0",
            "https://" + "a".repeat(2049)).forEach { assertNull(PairingQrParser.parse(payload(url = it))) }
    }
}

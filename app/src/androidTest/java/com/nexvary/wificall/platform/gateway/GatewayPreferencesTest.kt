package com.nexvary.wificall.platform.gateway

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class GatewayPreferencesTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val preferences get() = GatewayPreferences(context)
    private val raw get() = context.getSharedPreferences("gateway_credentials", 0)
    private val credential = GatewayCredentials("https://gateway.example.org", "test-device", "private_pairing_token_0123456789_ABCDEFGHIJKLM")

    @Before fun startClean() { preferences.clear() }
    @After fun clean() { preferences.clear() }

    @Test fun encryptedPairingSurvivesNewInstanceAndClearsCompletely() {
        assertTrue(preferences.save(credential) is GatewayResult.Success)
        val persisted = GatewayPreferences(context).load()
        assertTrue(persisted is GatewayResult.Success)
        val restored = (persisted as GatewayResult.Success).value!!
        assertEquals(credential.baseUrl, restored.baseUrl)
        assertEquals(credential.deviceId, restored.deviceId)
        assertEquals(credential.token, restored.token)
        val stored = raw.all.toString()
        assertFalse(stored.contains(credential.token))
        assertFalse(stored.contains(credential.deviceId))
        assertFalse(stored.contains(credential.baseUrl))
        assertTrue(preferences.recordReportSuccess(123456789L) is GatewayResult.Success)
        assertEquals(123456789L, preferences.lastReportAt())
        assertTrue(preferences.clear() is GatewayResult.Success)
        assertTrue(raw.all.isEmpty())
        assertNull((GatewayPreferences(context).load() as GatewayResult.Success).value)
    }

    @Test fun repeatedEncryptionUsesFreshRandomIvAndTamperingFailsClosed() {
        assertTrue(preferences.save(credential) is GatewayResult.Success)
        val first = raw.getString("encrypted_pairing", null)!!
        assertTrue(preferences.save(credential) is GatewayResult.Success)
        val second = raw.getString("encrypted_pairing", null)!!
        assertNotEquals(first, second)
        val bytes = android.util.Base64.decode(second, android.util.Base64.NO_WRAP)
        bytes[bytes.lastIndex] = (bytes.last().toInt() xor 1).toByte()
        raw.edit().putString("encrypted_pairing", android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)).commit()
        assertEquals(GatewayResult.Failure(GatewayError.STORAGE), preferences.load())
    }
}

package com.nexvary.wificall.platform.gateway

import org.junit.Assert.*
import org.junit.Test

class PhoneAkaAdapterTest {
    private val rand = "00112233445566778899AABBCCDDEEFF"
    private val autn = "FFEEDDCCBBAA99887766554433221100"
    private fun success(resLength: Int = 8) = byteArrayOf(0xdb.toByte(), resLength.toByte()) + ByteArray(resLength) { 1 } +
        byteArrayOf(16) + ByteArray(16) { 2 } + byteArrayOf(16) + ByteArray(16) { 3 }
    private class Fixture : PhoneAkaPlatform {
        var available = true; var permission = true; var ids = listOf(41); var privilege = true
        var calls = 0; var selected: Int? = null; var challenge: ByteArray? = null
        var response: String? = null; var denied = false
        override fun available() = available
        override fun permissionGranted() = permission
        override fun activeSubscriptions() = ids
        override fun carrierPrivileges(subscriptionId: Int) = privilege
        override fun authenticate(subscriptionId: Int, challenge: ByteArray): String? {
            calls++; selected = subscriptionId; this.challenge = challenge.copyOf()
            if (denied) throw SecurityException()
            return response
        }
    }

    @Test fun challengeUsesLengthRandLengthAutnAndExactSelectedSubscription() {
        val fixture = Fixture().apply { response = java.util.Base64.getEncoder().encodeToString(success()) }
        val result = PhoneAkaAdapter(fixture).authenticate(41, rand, autn)
        assertTrue(result is PhoneAkaResult.Success)
        assertEquals(41, fixture.selected)
        assertEquals(1, fixture.calls)
        assertArrayEquals(PhoneAkaCodec.challenge(rand, autn), fixture.challenge)
        assertEquals(34, fixture.challenge!!.size)
        assertEquals(16, fixture.challenge!![0].toInt()); assertEquals(16, fixture.challenge!![17].toInt())
        result.destroy()
        val success = result as PhoneAkaResult.Success
        assertTrue((success.res + success.ck + success.ik).all { it == 0.toByte() })
    }

    @Test fun everyAuthorizationFailurePreventsSimApiCalls() {
        val cases = listOf(
            Fixture().apply { available = false } to PhoneAkaError.TELEPHONY_UNAVAILABLE,
            Fixture().apply { permission = false } to PhoneAkaError.PERMISSION_REQUIRED,
            Fixture().apply { ids = listOf(72) } to PhoneAkaError.NO_ACTIVE_SIM,
            Fixture().apply { privilege = false } to PhoneAkaError.CARRIER_PRIVILEGE_REQUIRED)
        cases.forEach { (fixture, error) ->
            assertEquals(PhoneAkaResult.Failure(error), PhoneAkaAdapter(fixture).authenticate(41, rand, autn))
            assertEquals(0, fixture.calls)
        }
        val invalid = Fixture()
        assertEquals(PhoneAkaResult.Failure(PhoneAkaError.INVALID_CHALLENGE), PhoneAkaAdapter(invalid).authenticate(41, "00", autn))
        assertEquals(0, invalid.calls)
    }

    @Test fun nullMalformedAndSecurityResponsesRemainDistinct() {
        val fixture = Fixture()
        assertEquals(PhoneAkaResult.Failure(PhoneAkaError.NULL_RESPONSE), PhoneAkaAdapter(fixture).authenticate(41, rand, autn))
        fixture.response = "!notbase64!"
        assertEquals(PhoneAkaResult.Failure(PhoneAkaError.MALFORMED_RESPONSE), PhoneAkaAdapter(fixture).authenticate(41, rand, autn))
        fixture.denied = true
        assertEquals(PhoneAkaResult.Failure(PhoneAkaError.SECURITY_DENIED), PhoneAkaAdapter(fixture).authenticate(41, rand, autn))
    }

    @Test fun codecAcceptsOnlyValidDbDcAndDocumentedOptionalKc() {
        listOf(4, 8, 16).forEach { assertTrue(PhoneAkaCodec.parse(success(it)) is PhoneAkaResult.Success) }
        val withKc = success() + byteArrayOf(8) + ByteArray(8) { 4 }
        val result = PhoneAkaCodec.parse(withKc)
        assertArrayEquals(success(), PhoneAkaCodec.serialize(result))
        listOf(success(3), success(17), success().dropLast(1).toByteArray(), success() + byteArrayOf(0),
            success() + byteArrayOf(8) + ByteArray(9), byteArrayOf(0xdc.toByte(), 14) + ByteArray(15)).forEach {
            assertEquals(PhoneAkaResult.Failure(PhoneAkaError.MALFORMED_RESPONSE), PhoneAkaCodec.parse(it))
        }
        val sync = PhoneAkaCodec.parse(byteArrayOf(0xdc.toByte(), 14) + ByteArray(14) { 5 })
        assertTrue(sync is PhoneAkaResult.SynchronizationFailure)
        sync.destroy()
        assertTrue((sync as PhoneAkaResult.SynchronizationFailure).auts.all { it == 0.toByte() })
    }
}

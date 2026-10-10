package com.nexvary.wificall.platform.gateway

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.telephony.SubscriptionManager
import android.telephony.TelephonyManager
import android.util.Base64
import androidx.core.content.ContextCompat

enum class PhoneAkaError {
    PERMISSION_REQUIRED, NO_ACTIVE_SIM, CARRIER_PRIVILEGE_REQUIRED, TELEPHONY_UNAVAILABLE,
    UNSUPPORTED, INVALID_CHALLENGE, NULL_RESPONSE, MALFORMED_RESPONSE, SECURITY_DENIED
}
sealed interface PhoneAkaResult {
    fun destroy() { }
    class Success(val res: ByteArray, val ck: ByteArray, val ik: ByteArray) : PhoneAkaResult {
        override fun destroy() { res.fill(0); ck.fill(0); ik.fill(0) }
        override fun toString() = "PhoneAkaResult.Success(redacted)"
    }
    class SynchronizationFailure(val auts: ByteArray) : PhoneAkaResult {
        override fun destroy() { auts.fill(0) }
        override fun toString() = "PhoneAkaResult.SynchronizationFailure(redacted)"
    }
    data class Failure(val error: PhoneAkaError) : PhoneAkaResult
}

/** Pure wire codec; no long-term SIM secret is accepted or returned. */
object PhoneAkaCodec {
    fun challenge(rand: String, autn: String): ByteArray? {
        if (!rand.matches(Regex("[0-9A-Fa-f]{32}")) || !autn.matches(Regex("[0-9A-Fa-f]{32}"))) return null
        fun bytes(hex: String) = ByteArray(16) { hex.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
        return byteArrayOf(16) + bytes(rand) + byteArrayOf(16) + bytes(autn)
    }

    fun serialize(result: PhoneAkaResult): ByteArray? = when (result) {
        is PhoneAkaResult.Success -> byteArrayOf(0xdb.toByte(), result.res.size.toByte()) + result.res +
            byteArrayOf(16) + result.ck + byteArrayOf(16) + result.ik
        is PhoneAkaResult.SynchronizationFailure -> byteArrayOf(0xdc.toByte(), 14) + result.auts
        is PhoneAkaResult.Failure -> null
    }

    fun parse(bytes: ByteArray): PhoneAkaResult {
        fun invalid() = PhoneAkaResult.Failure(PhoneAkaError.MALFORMED_RESPONSE)
        if (bytes.isEmpty() || bytes.size > 128) return invalid()
        if ((bytes[0].toInt() and 255) == 0xdc) {
            return if (bytes.size == 16 && bytes[1].toInt() == 14)
                PhoneAkaResult.SynchronizationFailure(bytes.copyOfRange(2, 16)) else invalid()
        }
        if ((bytes[0].toInt() and 255) != 0xdb) return invalid()
        var offset = 1
        fun segment(min: Int, max: Int): IntRange? {
            if (offset >= bytes.size) return null
            val size = bytes[offset++].toInt() and 255
            if (size !in min..max || offset + size > bytes.size) return null
            val range = offset until offset + size
            offset += size
            return range
        }
        val res = segment(4, 16) ?: return invalid()
        val ck = segment(16, 16) ?: return invalid()
        val ik = segment(16, 16) ?: return invalid()
        // AOSP CarrierApiTest documents optional [length][Kc]. Validate eight bytes,
        // discard them, and reject every other trailing byte. No GSM adapter is exposed.
        if (offset < bytes.size && segment(8, 8) == null) return invalid()
        if (offset != bytes.size) return invalid()
        return PhoneAkaResult.Success(bytes.copyOfRange(res.first, res.last + 1),
            bytes.copyOfRange(ck.first, ck.last + 1), bytes.copyOfRange(ik.first, ik.last + 1))
    }
}

internal interface PhoneAkaPlatform {
    fun available(): Boolean
    fun permissionGranted(): Boolean
    fun activeSubscriptions(): List<Int>
    fun carrierPrivileges(subscriptionId: Int): Boolean
    fun authenticate(subscriptionId: Int, challenge: ByteArray): String?
}

/** Synchronous authorized ICC adapter. Invoke on IO, in an explicitly bounded foreground session. */
class PhoneAkaAdapter internal constructor(private val platform: PhoneAkaPlatform) {
    constructor(context: Context) : this(AndroidPhoneAkaPlatform(context.applicationContext))

    fun authenticate(subscriptionId: Int, rand: String, autn: String): PhoneAkaResult {
        val challenge = PhoneAkaCodec.challenge(rand, autn)
            ?: return PhoneAkaResult.Failure(PhoneAkaError.INVALID_CHALLENGE)
        var response: ByteArray? = null
        return try {
            when {
                !platform.available() -> PhoneAkaResult.Failure(PhoneAkaError.TELEPHONY_UNAVAILABLE)
                !platform.permissionGranted() -> PhoneAkaResult.Failure(PhoneAkaError.PERMISSION_REQUIRED)
                subscriptionId !in platform.activeSubscriptions() -> PhoneAkaResult.Failure(PhoneAkaError.NO_ACTIVE_SIM)
                !platform.carrierPrivileges(subscriptionId) -> PhoneAkaResult.Failure(PhoneAkaError.CARRIER_PRIVILEGE_REQUIRED)
                else -> {
                    val encoded = platform.authenticate(subscriptionId, challenge)
                    if (encoded == null) PhoneAkaResult.Failure(PhoneAkaError.NULL_RESPONSE) else {
                        val normalized = encoded.replace("\r", "").replace("\n", "")
                        if (normalized.length !in 4..256 || !normalized.matches(Regex("[A-Za-z0-9+/]+={0,2}"))) {
                            PhoneAkaResult.Failure(PhoneAkaError.MALFORMED_RESPONSE)
                        } else {
                            response = java.util.Base64.getDecoder().decode(normalized)
                            PhoneAkaCodec.parse(response!!)
                        }
                    }
                }
            }
        } catch (_: SecurityException) { PhoneAkaResult.Failure(PhoneAkaError.SECURITY_DENIED)
        } catch (_: UnsupportedOperationException) { PhoneAkaResult.Failure(PhoneAkaError.UNSUPPORTED)
        } catch (_: IllegalArgumentException) { PhoneAkaResult.Failure(PhoneAkaError.MALFORMED_RESPONSE)
        } catch (_: RuntimeException) { PhoneAkaResult.Failure(PhoneAkaError.TELEPHONY_UNAVAILABLE)
        } finally { challenge.fill(0); response?.fill(0) }
    }
}

// Lint cannot infer the runtime permission and carrier-privilege guards repeated before each API call.
@android.annotation.SuppressLint("MissingPermission")
private class AndroidPhoneAkaPlatform(private val context: Context) : PhoneAkaPlatform {
    override fun available() = context.packageManager.hasSystemFeature(PackageManager.FEATURE_TELEPHONY_SUBSCRIPTION) &&
        context.getSystemService(TelephonyManager::class.java) != null && context.getSystemService(SubscriptionManager::class.java) != null
    override fun permissionGranted() = ContextCompat.checkSelfPermission(context, Manifest.permission.READ_PHONE_STATE) == PackageManager.PERMISSION_GRANTED
    override fun activeSubscriptions() = context.getSystemService(SubscriptionManager::class.java)?.activeSubscriptionInfoList.orEmpty().map { it.subscriptionId }
    override fun carrierPrivileges(subscriptionId: Int) = context.getSystemService(TelephonyManager::class.java)
        .createForSubscriptionId(subscriptionId).hasCarrierPrivileges()
    override fun authenticate(subscriptionId: Int, challenge: ByteArray): String? {
        // Recheck directly before the public API, preventing a stale UI capability from authorizing a call.
        if (!permissionGranted() || subscriptionId !in activeSubscriptions()) throw SecurityException()
        val manager = context.getSystemService(TelephonyManager::class.java).createForSubscriptionId(subscriptionId)
        if (!manager.hasCarrierPrivileges()) throw SecurityException()
        return manager.getIccAuthentication(TelephonyManager.APPTYPE_USIM,
            TelephonyManager.AUTHTYPE_EAP_AKA, Base64.encodeToString(challenge, Base64.NO_WRAP))
    }
}

package com.nexvary.wificall.platform.gateway

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Only gateway pairing credentials; never SIM authentication material. Exclude this file from backups. */
class GatewayPreferences(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences("gateway_credentials", Context.MODE_PRIVATE)
    private val alias = "nexvary_gateway_pairing_v1"

    @Synchronized fun load(): GatewayResult<GatewayCredentials?> = try {
        val encoded = preferences.getString("encrypted_pairing", null)
        if (encoded == null) GatewayResult.Success(null) else {
            val packed = Base64.decode(encoded, Base64.NO_WRAP)
            require(packed.size in 29..8192)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, packed.copyOfRange(0, 12)))
            cipher.updateAAD(alias.toByteArray(Charsets.UTF_8))
            val json = JSONObject(String(cipher.doFinal(packed.copyOfRange(12, packed.size)), Charsets.UTF_8))
            val base = GatewayAddress.normalize(json.getString("base")) ?: error("Invalid gateway address")
            val id = json.getString("device")
            val token = json.getString("token")
            require(GatewayValidation.deviceId(id) && GatewayValidation.token(token))
            GatewayResult.Success(GatewayCredentials(base, id, token))
        }
    } catch (_: Exception) { GatewayResult.Failure(GatewayError.STORAGE) }

    @Synchronized fun save(credentials: GatewayCredentials): GatewayResult<Unit> = try {
        require(GatewayAddress.normalize(credentials.baseUrl) != null)
        require(GatewayValidation.deviceId(credentials.deviceId) && GatewayValidation.token(credentials.token))
        val plaintext = JSONObject().put("base", credentials.baseUrl).put("device", credentials.deviceId)
            .put("token", credentials.token).toString().toByteArray(Charsets.UTF_8)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        cipher.updateAAD(alias.toByteArray(Charsets.UTF_8))
        val packed = cipher.iv + cipher.doFinal(plaintext)
        if (preferences.edit().putString("encrypted_pairing", Base64.encodeToString(packed, Base64.NO_WRAP))
                .remove("last_report_at").commit()) GatewayResult.Success(Unit)
        else GatewayResult.Failure(GatewayError.STORAGE)
    } catch (_: Exception) { GatewayResult.Failure(GatewayError.STORAGE) }

    /** Call only after confirmed remote revocation, or an explicit local-forget action. */
    @Synchronized fun clear(): GatewayResult<Unit> =
        if (preferences.edit().clear().commit()) GatewayResult.Success(Unit) else GatewayResult.Failure(GatewayError.STORAGE)

    fun lastReportAt(): Long? = preferences.getLong("last_report_at", 0).takeIf { it > 0 }

    @Synchronized fun recordReportSuccess(epochMillis: Long): GatewayResult<Unit> =
        if (epochMillis > 0 && preferences.edit().putLong("last_report_at", epochMillis).commit()) GatewayResult.Success(Unit)
        else GatewayResult.Failure(GatewayError.STORAGE)

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val existing = store.getKey(alias, null) as? SecretKey
        if (existing != null) return existing
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true)
                .build())
        }.generateKey()
    }
}

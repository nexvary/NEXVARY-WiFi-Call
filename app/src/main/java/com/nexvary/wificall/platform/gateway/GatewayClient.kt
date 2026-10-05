package com.nexvary.wificall.platform.gateway

import com.nexvary.wificall.BuildConfig
import com.nexvary.wificall.platform.PhoneAsSimCapability
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.net.SocketTimeoutException
import javax.net.ssl.SSLException

enum class GatewayError { INVALID_URL, INVALID_CODE, INVALID_REPORT, UNAUTHORIZED, REJECTED, NETWORK, TLS, INVALID_RESPONSE, STORAGE }
sealed interface GatewayResult<out T> {
    data class Success<T>(val value: T) : GatewayResult<T>
    data class Failure(val error: GatewayError) : GatewayResult<Nothing>
}

/** A bearer credential is never rendered, exported or included in logs. */
class GatewayCredentials(val baseUrl: String, val deviceId: String, val token: String) {
    override fun toString() = "GatewayCredentials(redacted)"
}

internal object GatewayValidation {
    fun pairCode(value: String) = value.matches(Regex("[A-Za-z0-9_-]{22,128}"))
    fun deviceId(value: String) = value.matches(Regex("[A-Za-z0-9_-]{1,128}"))
    fun token(value: String) = value.matches(Regex("[A-Za-z0-9._~-]{32,128}"))
}

enum class GatewayNetwork { WIFI, CELLULAR, OTHER, NONE, UNKNOWN }
data class GatewayReport(
    val simCount: Int,
    val selectedSlot: Int?,
    val network: GatewayNetwork,
    val phoneAsSim: PhoneAsSimCapability?,
    val appVersion: String = BuildConfig.VERSION_NAME,
    val androidApi: Int
) {
    fun isValid() = simCount in 0..8 && (selectedSlot == null || selectedSlot in 0..7) &&
        (simCount != 0 || selectedSlot == null) && appVersion.matches(Regex("[A-Za-z0-9][A-Za-z0-9.-]{0,63}")) && androidApi in 26..100
}

/** HTTPS only. Relative paths, embedded credentials, query strings and fragments are rejected. */
object GatewayAddress {
    fun normalize(value: String): String? = try {
        val uri = URI(value.trim())
        if (!uri.scheme.equals("https", ignoreCase = true) || uri.host.isNullOrBlank() ||
            uri.rawUserInfo != null || uri.rawQuery != null || uri.rawFragment != null ||
            uri.port !in -1..65535 || uri.port == 0 || uri.rawPath !in listOf("", "/")) null
        else URI("https", null, uri.host, uri.port, null, null, null).toASCIIString()
    } catch (_: Exception) { null }
}

/** Synchronous requests: callers must use an IO dispatcher. Standard Android TLS verification only. */
class GatewayClient internal constructor(private val connectionFactory: (URL) -> HttpURLConnection) {
    constructor() : this({ url -> url.openConnection() as HttpURLConnection })
    fun pair(baseUrl: String, code: String): GatewayResult<GatewayCredentials> {
        val base = GatewayAddress.normalize(baseUrl) ?: return GatewayResult.Failure(GatewayError.INVALID_URL)
        if (!GatewayValidation.pairCode(code)) return GatewayResult.Failure(GatewayError.INVALID_CODE)
        return when (val response = post(base, "/api/phone/pair", JSONObject().put("code", code), null)) {
            is GatewayResult.Failure -> response
            is GatewayResult.Success -> try {
                val json = JSONObject(response.value)
                val id = json.getString("device_id")
                val token = json.getString("token")
                if (!GatewayValidation.deviceId(id) || !GatewayValidation.token(token)) {
                    GatewayResult.Failure(GatewayError.INVALID_RESPONSE)
                } else GatewayResult.Success(GatewayCredentials(base, id, token))
            } catch (_: Exception) { GatewayResult.Failure(GatewayError.INVALID_RESPONSE) }
        }
    }

    fun report(credentials: GatewayCredentials, report: GatewayReport): GatewayResult<Unit> {
        if (!report.isValid()) return GatewayResult.Failure(GatewayError.INVALID_REPORT)
        val json = JSONObject()
            .put("schema_version", 1)
            .put("sim_count", report.simCount)
            .put("selected_slot", report.selectedSlot ?: JSONObject.NULL)
            .put("network", report.network.name)
            .put("phone_as_sim", report.phoneAsSim?.name ?: "UNKNOWN")
            .put("app_version", report.appVersion)
            .put("android_api", report.androidApi)
        return unitResult(post(credentials.baseUrl, "/api/phone/report", json, credentials.token))
    }

    fun disconnect(credentials: GatewayCredentials): GatewayResult<Unit> =
        unitResult(post(credentials.baseUrl, "/api/phone/disconnect", JSONObject(), credentials.token))

    private fun unitResult(result: GatewayResult<String>): GatewayResult<Unit> = when (result) {
        is GatewayResult.Failure -> result
        is GatewayResult.Success -> try {
            val json = JSONObject(result.value)
            if (json.opt("ok") == true) GatewayResult.Success(Unit)
            else GatewayResult.Failure(GatewayError.INVALID_RESPONSE)
        } catch (_: Exception) { GatewayResult.Failure(GatewayError.INVALID_RESPONSE) }
    }

    private fun post(baseUrl: String, path: String, json: JSONObject, token: String?): GatewayResult<String> {
        val base = GatewayAddress.normalize(baseUrl) ?: return GatewayResult.Failure(GatewayError.INVALID_URL)
        if (token != null && !GatewayValidation.token(token)) return GatewayResult.Failure(GatewayError.UNAUTHORIZED)
        var connection: HttpURLConnection? = null
        return try {
            connection = connectionFactory(URI(base + path).toURL())
            connection.requestMethod = "POST"
            connection.connectTimeout = 10_000
            connection.readTimeout = 10_000
            connection.instanceFollowRedirects = false
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.setRequestProperty("Accept", "application/json")
            if (token != null) connection.setRequestProperty("Authorization", "Bearer $token")
            val bytes = json.toString().toByteArray(Charsets.UTF_8)
            connection.setFixedLengthStreamingMode(bytes.size)
            connection.outputStream.use { it.write(bytes) }
            when (connection.responseCode) {
                401 -> GatewayResult.Failure(GatewayError.UNAUTHORIZED)
                403 -> GatewayResult.Failure(GatewayError.REJECTED)
                in 200..299 -> {
                    val body = ByteArrayOutputStream()
                    connection.inputStream.use { stream ->
                        val buffer = ByteArray(1024)
                        while (true) {
                            val count = stream.read(buffer)
                            if (count < 0) break
                            if (body.size() + count > 8192) return GatewayResult.Failure(GatewayError.INVALID_RESPONSE)
                            body.write(buffer, 0, count)
                        }
                    }
                    GatewayResult.Success(body.toString("UTF-8"))
                }
                else -> GatewayResult.Failure(GatewayError.REJECTED)
            }
        } catch (_: SSLException) {
            GatewayResult.Failure(GatewayError.TLS)
        } catch (_: SocketTimeoutException) {
            GatewayResult.Failure(GatewayError.NETWORK)
        } catch (_: IOException) {
            GatewayResult.Failure(GatewayError.NETWORK)
        } catch (_: Exception) {
            GatewayResult.Failure(GatewayError.INVALID_RESPONSE)
        } finally { connection?.disconnect() }
    }
}

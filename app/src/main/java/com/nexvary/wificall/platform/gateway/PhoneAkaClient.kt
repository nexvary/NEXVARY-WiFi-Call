package com.nexvary.wificall.platform.gateway

import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import javax.net.ssl.SSLException

class PhoneAkaSession(val id: String, val expiresAt: Long, val selectedSlot: Int) {
    internal val localDeadlineNanos = System.nanoTime() + java.util.concurrent.TimeUnit.MINUTES.toNanos(5)
    override fun toString() = "PhoneAkaSession(redacted)"
}
class PhoneAkaChallenge(val id: String, val rand: String, val autn: String, val expiresAt: Long) {
    override fun toString() = "PhoneAkaChallenge(redacted)"
}
/** Ephemeral HTTPS broker only. No AKA payload, challenge or response is persisted or logged. */
class PhoneAkaClient internal constructor(private val factory: (URL) -> HttpURLConnection) {
    constructor() : this({ it.openConnection() as HttpURLConnection })
    private fun identifier(value: Any?) = value is String && value.matches(Regex("[A-Za-z0-9_-]{32,128}"))
    private fun fields(json: JSONObject, expected: Set<String>) = json.keys().asSequence().toSet() == expected
    private fun validSession(session: PhoneAkaSession) = identifier(session.id) && session.selectedSlot in 0..7 &&
        System.currentTimeMillis() / 1000 < session.expiresAt && System.nanoTime() < session.localDeadlineNanos
    fun start(credentials: GatewayCredentials, slot: Int): GatewayResult<PhoneAkaSession> {
        if (slot !in 0..7) return GatewayResult.Failure(GatewayError.INVALID_REPORT)
        return when (val result = post(credentials, "session", JSONObject().put("selected_slot", slot))) {
            is GatewayResult.Failure -> result
            is GatewayResult.Success -> {
                val json = result.value
                val id = json.opt("session_id")
                val expiry = integral(json.opt("expires_at"))
                val now = System.currentTimeMillis() / 1000
                if (!fields(json, setOf("session_id", "selected_slot", "expires_at")) || json.opt("selected_slot") != slot ||
                    !identifier(id) || expiry == null || expiry !in (now + 1)..(now + 300)) invalid()
                else GatewayResult.Success(PhoneAkaSession(id as String, expiry, slot))
            }
        }
    }
    fun poll(credentials: GatewayCredentials, session: PhoneAkaSession): GatewayResult<PhoneAkaChallenge?> {
        if (!validSession(session)) return GatewayResult.Failure(GatewayError.INVALID_REPORT)
        return when (val result = post(credentials, "poll", JSONObject().put("session_id", session.id))) {
            is GatewayResult.Failure -> result
            is GatewayResult.Success -> {
                val json = result.value
                if (!fields(json, setOf("challenge"))) invalid()
                else if (json.isNull("challenge")) GatewayResult.Success(null)
                else {
                    val challenge = json.optJSONObject("challenge")
                    val id = challenge?.opt("challenge_id")
                    val rand = challenge?.opt("rand")
                    val autn = challenge?.opt("autn")
                    val expiry = integral(challenge?.opt("expires_at"))
                    val now = System.currentTimeMillis() / 1000
                    val scopeMatches = challenge?.let {
                        fields(it, setOf("session_id", "challenge_id", "selected_slot", "rand", "autn", "expires_at")) &&
                            it.opt("session_id") == session.id && it.opt("selected_slot") == session.selectedSlot
                    } == true
                    if (!scopeMatches || !identifier(id) || rand !is String || autn !is String || PhoneAkaCodec.challenge(rand, autn) == null ||
                        expiry == null || expiry !in (now + 1)..(now + 30) || expiry > session.expiresAt) invalid()
                    else GatewayResult.Success(PhoneAkaChallenge(id as String, rand, autn, expiry))
                }
            }
        }
    }

    fun submit(credentials: GatewayCredentials, session: PhoneAkaSession, challenge: PhoneAkaChallenge,
               response: PhoneAkaResult): GatewayResult<Unit> {
        val now = System.currentTimeMillis() / 1000
        if (!validSession(session) || !identifier(challenge.id) || challenge.expiresAt <= now ||
            challenge.expiresAt > session.expiresAt || challenge.expiresAt > now + 30) {
            return GatewayResult.Failure(GatewayError.INVALID_REPORT)
        }
        val state = when (response) {
            is PhoneAkaResult.Success -> "SUCCESS"
            is PhoneAkaResult.SynchronizationFailure -> "SYNC_FAILURE"
            is PhoneAkaResult.Failure -> when (response.error) {
                PhoneAkaError.NULL_RESPONSE -> "AUTHENTICATION_FAILED"
                PhoneAkaError.INVALID_CHALLENGE, PhoneAkaError.MALFORMED_RESPONSE -> "MALFORMED_RESPONSE"
                PhoneAkaError.SECURITY_DENIED -> "AUTHENTICATION_FAILED"
                else -> response.error.name
            }
        }
        val bytes = PhoneAkaCodec.serialize(response)
        return try {
            val json = JSONObject().put("session_id", session.id).put("challenge_id", challenge.id).put("state", state)
                .put("payload", if (bytes == null) JSONObject.NULL else java.util.Base64.getEncoder().encodeToString(bytes))
            acknowledged(post(credentials, "result", json))
        } finally { bytes?.fill(0) }
    }
    fun stop(credentials: GatewayCredentials, session: PhoneAkaSession) =
        acknowledged(post(credentials, "stop", JSONObject().put("session_id", session.id)))
    private fun acknowledged(result: GatewayResult<JSONObject>): GatewayResult<Unit> = when (result) {
        is GatewayResult.Failure -> result
        is GatewayResult.Success -> if (fields(result.value, setOf("ok")) && result.value.opt("ok") == true) GatewayResult.Success(Unit) else invalid()
    }
    private fun integral(value: Any?): Long? = when (value) { is Int -> value.toLong(); is Long -> value; else -> null }
    private fun invalid() = GatewayResult.Failure(GatewayError.INVALID_RESPONSE)
    private fun post(credentials: GatewayCredentials, action: String, body: JSONObject): GatewayResult<JSONObject> {
        val base = GatewayAddress.normalize(credentials.baseUrl) ?: return GatewayResult.Failure(GatewayError.INVALID_URL)
        if (!GatewayValidation.token(credentials.token)) return GatewayResult.Failure(GatewayError.UNAUTHORIZED)
        var connection: HttpURLConnection? = null
        return try {
            connection = factory(URI("$base/api/phone/aka/$action").toURL())
            connection.requestMethod = "POST"; connection.connectTimeout = 10_000; connection.readTimeout = 10_000
            connection.instanceFollowRedirects = false; connection.doOutput = true
            connection.setRequestProperty("Authorization", "Bearer ${credentials.token}")
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.setRequestProperty("Accept", "application/json")
            val request = body.toString().toByteArray(Charsets.UTF_8)
            connection.setFixedLengthStreamingMode(request.size)
            try { connection.outputStream.use { it.write(request) } } finally { request.fill(0) }
            when (connection.responseCode) {
                401 -> GatewayResult.Failure(GatewayError.UNAUTHORIZED)
                403 -> GatewayResult.Failure(GatewayError.REJECTED)
                in 200..299 -> {
                    val bytes = ByteArrayOutputStream()
                    connection.inputStream.use { input ->
                        val buffer = ByteArray(1024)
                        while (true) {
                            val count = input.read(buffer)
                            if (count < 0) break
                            if (bytes.size() + count > 8192) return invalid()
                            bytes.write(buffer, 0, count)
                        }
                    }
                    GatewayResult.Success(JSONObject(bytes.toString("UTF-8")))
                }
                else -> GatewayResult.Failure(GatewayError.REJECTED)
            }
        } catch (_: SSLException) { GatewayResult.Failure(GatewayError.TLS)
        } catch (_: java.io.IOException) { GatewayResult.Failure(GatewayError.NETWORK)
        } catch (_: Exception) { invalid()
        } finally { connection?.disconnect() }
    }
}

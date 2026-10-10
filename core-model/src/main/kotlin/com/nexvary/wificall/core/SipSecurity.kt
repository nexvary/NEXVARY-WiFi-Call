package com.nexvary.wificall.core

/** Short-lived coturn REST credentials. Never persist or serialize this object. */
class SecureTurnSettings private constructor(
    val host: String,
    val port: Int,
    val username: String,
    val password: String,
    val expiresAtSeconds: Long
) {
    val sdkServer: String get() = "$host:$port"
    fun isFresh(nowSeconds: Long): Boolean = nowSeconds > 0 && expiresAtSeconds > nowSeconds
    override fun toString() = "SecureTurnSettings(credentials=redacted)"

    companion object {
        fun parse(endpoint: String, username: String, password: String, nowSeconds: Long): SecureTurnSettings {
            val match = Regex("turns:([A-Za-z0-9.-]+):([0-9]{1,5})(?:\\?transport=tcp)?").matchEntire(endpoint)
                ?: throw IllegalArgumentException("TURN_TLS_ENDPOINT_REQUIRED")
            val host = match.groupValues[1]
            val port = match.groupValues[2].toIntOrNull() ?: 0
            require(InternalDialPolicy.validHost(host) && host.split('.').all { label ->
                label.length in 1..63 && label.first().isLetterOrDigit() && label.last().isLetterOrDigit()
            } && InternalDialPolicy.validPort(port)) { "INVALID_TURN_SERVER" }
            val user = Regex("([0-9]{1,19}):([A-Za-z0-9._-]{1,96})").matchEntire(username)
                ?: throw IllegalArgumentException("EPHEMERAL_TURN_USERNAME_REQUIRED")
            val expiry = user.groupValues[1].toLongOrNull() ?: 0L
            require(nowSeconds in 1..(Long.MAX_VALUE - 3600) && expiry > nowSeconds && expiry <= nowSeconds + 3600) {
                "TURN_CREDENTIALS_EXPIRED_OR_TOO_LONG"
            }
            require(password.matches(Regex("[A-Za-z0-9+/=]{16,256}"))) { "INVALID_TURN_CREDENTIAL" }
            return SecureTurnSettings(host, port, username, password, expiry)
        }
    }
}

object DtmfPolicy {
    fun validDigit(digit: Char): Boolean = digit in '0'..'9' || digit == '*' || digit == '#'
}

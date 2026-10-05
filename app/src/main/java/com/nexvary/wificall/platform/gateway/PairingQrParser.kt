package com.nexvary.wificall.platform.gateway

import org.json.JSONObject
import org.json.JSONTokener

/** An untrusted QR only supplies a candidate pairing form; it never authorizes a request. */
class PairingQrPayload(val url: String, val code: String) {
    override fun toString() = "PairingQrPayload(redacted)"
}

/** Android JSONObject is lenient, so require strict flat JSON syntax before decoding values. */
internal object PairingQrShape {
    private const val stringToken = "\"(?:[^\"\\\\\\x00-\\x1F]|\\\\(?:[\"\\\\/bfnrt]|u[0-9A-Fa-f]{4}))*\""
    private const val scalarToken = "(?:$stringToken|-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null)"
    private const val fieldToken = "$stringToken[ \\t\\r\\n]*:[ \\t\\r\\n]*$scalarToken"
    private val objectPattern = Regex("\\A[ \\t\\r\\n]*\\{[ \\t\\r\\n]*$fieldToken(?:[ \\t\\r\\n]*,[ \\t\\r\\n]*$fieldToken)*[ \\t\\r\\n]*\\}[ \\t\\r\\n]*\\z")
    val fields = Regex("($stringToken)[ \\t\\r\\n]*:[ \\t\\r\\n]*($scalarToken)")
    fun valid(raw: String) = raw.length in 1..4096 && objectPattern.matches(raw)
}

object PairingQrParser {
    fun parse(raw: String?): PairingQrPayload? = try {
        if (raw == null || !PairingQrShape.valid(raw)) null else {
            val names = PairingQrShape.fields.findAll(raw).map {
                JSONTokener(it.groupValues[1]).nextValue() as? String
            }.toList()
            val required = setOf("type", "version", "url", "code")
            if (names.size != 4 || names.toSet() != required) null else {
                val json = JSONObject(raw)
                val type = json.opt("type")
                val version = json.opt("version")
                val url = json.opt("url")
                val code = json.opt("code")
                if (type != "nexvary-pairing" || version !is Int || version != 1 ||
                    url !is String || url.length > 2048 || code !is String || !GatewayValidation.pairCode(code)) null
                else GatewayAddress.normalize(url)?.let { PairingQrPayload(it, code) }
            }
        }
    } catch (_: Exception) { null }
}

package com.nexvary.wificall.core

object DiagnosticRedactor {
    private val phone=Regex("""(?<!\d)\+?\d[\d -]{6,}\d(?!\d)""")
    private val imsi=Regex("""(?<!\d)\d{14,16}(?!\d)""")
    private val ipv4=Regex("""\b(?:\d{1,3}\.){3}\d{1,3}\b""")
    fun redact(text:String):String = text
        .replace(imsi,"[REDACTED_SUBSCRIBER_ID]")
        .replace(phone,"[REDACTED_PHONE]")
        .replace(ipv4,"[REDACTED_IP]")
}

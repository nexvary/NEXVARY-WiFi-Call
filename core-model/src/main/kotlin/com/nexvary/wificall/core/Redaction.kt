package com.nexvary.wificall.core

object DiagnosticRedactor {
    // Unlabelled numeric diagnostics (dates, timestamps, ports and MCC/MNC) are not phones.
    private val internationalPhone=Regex("""(?<![\w+])\+\d[\d ()-]*\d(?!\d)""")
    private val labelledPhone=Regex("""(?i)(\b(?:phone|msisdn|telephone|tel)\s*[:=]?\s*)(\+?\d[\d ()-]*\d)""")
    private val labelledSubscriber=Regex("""(?i)(\b(?:imsi|iccid|subscriber[_ -]?id)\s*[:=]?\s*)\d{8,22}\b""")
    private val imsi=Regex("""(?<!\d)\d{14,16}(?!\d)""")
    private val ipv4=Regex("""\b(?:\d{1,3}\.){3}\d{1,3}\b""")
    private val ipv6=Regex("""(?<![\w:])(?:[a-fA-F0-9]{0,4}:){2,}[a-fA-F0-9]{0,4}(?:%[\w.~-]+)?(?![\w:])""")
    private val secret=Regex("""(?i)(\b(?:ki|opc|ck|ik|long[-_ ]term[-_ ]secret|rand|autn|res|auts|(?:ike|ipsec)[_ -]?(?:(?:encryption|integrity)[_ -]?)?key|sk[_ -]?(?:d|ai|ar|ei|er|pi|pr)|impi|impu)\s*[:=]\s*)(?:"[^"]*"|'[^']*'|\[[^\]\r\n]*\]|[a-f0-9]{2}(?:[ -]+[a-f0-9]{2})+\b|[^\s,;]+)""")
    private val authorization=Regex("""(?im)(\b(?:authorization|proxy-authorization)\s*:\s*)[^\r\n]+""")
    fun redact(text:String):String = text
        .replace(authorization) { it.groupValues[1]+"[REDACTED_SECRET]" }
        .replace(secret) { it.groupValues[1]+"[REDACTED_SECRET]" }
        .replace(labelledSubscriber) { it.groupValues[1]+"[REDACTED_SUBSCRIBER_ID]" }
        .replace(imsi,"[REDACTED_SUBSCRIBER_ID]")
        .replace(labelledPhone) { it.groupValues[1]+"[REDACTED_PHONE]" }
        .replace(internationalPhone) {
            if(it.value.count(Char::isDigit) in 7..15) "[REDACTED_PHONE]" else it.value
        }
        .replace(ipv4,"[REDACTED_IP]")
        .replace(ipv6) {
            // Avoid redacting clock times and six-group MAC addresses.
            if(it.value.contains("::") || it.value.substringBefore('%').count { c -> c == ':' } == 7)
                "[REDACTED_IP]" else it.value
        }
}

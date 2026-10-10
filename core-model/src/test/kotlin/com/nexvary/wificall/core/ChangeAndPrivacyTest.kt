package com.nexvary.wificall.core

import kotlin.test.*

class ChangeAndPrivacyTest {
    private val network = NetworkContext(true, true, false, false, false, null, 2)

    @Test fun explainsVpnAndValidationChange() {
        val after = network.copy(validated = false, vpn = true)
        val reasons = ChangeExplainer.compare(network, after).reasons
        assertTrue(ChangeReason.VPN_ENABLED in reasons)
        assertTrue(ChangeReason.VALIDATION_LOST in reasons)
    }

    @Test fun missingMeasurementsNeverImplyQualityChange() {
        QualityGrade.entries.forEach { measured ->
            assertTrue(ChangeExplainer.compare(network, network, measured, QualityGrade.UNKNOWN).reasons.isEmpty())
            assertTrue(ChangeExplainer.compare(network, network, QualityGrade.UNKNOWN, measured).reasons.isEmpty())
            assertTrue(ChangeExplainer.compare(network, network, null, measured).reasons.isEmpty())
        }
    }

    @Test fun measuredQualityImprovementAndDegradationRemainVisible() {
        assertEquals(listOf(ChangeReason.QUALITY_DEGRADED),
            ChangeExplainer.compare(network, network, QualityGrade.GOOD, QualityGrade.POOR).reasons)
        assertEquals(listOf(ChangeReason.QUALITY_IMPROVED),
            ChangeExplainer.compare(network, network, QualityGrade.FAIR, QualityGrade.EXCELLENT).reasons)
    }

    @Test fun redactsSubscriberAddressesAndPhones() {
        val text = "imsi 310260123456789 iccid=8901260123456789012 ip 192.168.1.8 phone +201001234567 tel: 01001234567 ipv6 2001:db8::1"
        val redacted = DiagnosticRedactor.redact(text)
        listOf("310260123456789", "8901260123456789012", "192.168.1.8", "201001234567", "01001234567", "2001:db8::1").forEach {
            assertFalse(redacted.contains(it), redacted)
        }
        assertTrue(DiagnosticRedactor.redact("call +44 20 7946 0958").contains("[REDACTED_PHONE]"))
    }

    @Test fun preservesDiagnosticDatesPortsMccMncAndClockTimes() {
        val text = "date=2026-10-05 epoch=1791158400 MCC=602 MNC=01 ports=500 4500 duration=12000000 clock=12:34:56 mac=aa:bb:cc:dd:ee:ff"
        assertEquals(text, DiagnosticRedactor.redact(text))
    }

    @Test fun unexpectedLongTermSecretIsRemovedFromExport() {
        val secret = "00112233445566778899aabbccddeeff"
        val redacted = DiagnosticRedactor.redact("Ki=$secret OPc: $secret")
        assertFalse(redacted.contains(secret))
        assertTrue(redacted.contains("[REDACTED_SECRET]"))
    }

    @Test fun protocolAuthenticationAndSubscriberIdentitiesAreRemoved() {
        val text = "RAND=abcdef AUTN=123456 RES='private response' IMPI=subscriber@example.org\nAuthorization: Digest username=private,response=abcdef"
        val redacted = DiagnosticRedactor.redact(text)
        listOf("abcdef", "123456", "private", "subscriber@example.org").forEach {
            assertFalse(redacted.contains(it), redacted)
        }
    }

    @Test fun akaAndIkeSessionKeysAreRemovedWithoutHidingStageNames() {
        val key = "00112233445566778899aabbccddeeff"
        val text = "CK=$key IK: $key IKE_KEY='$key' IPsec encryption key=$key SK_d=$key SK_ai=$key SK_ar=$key SK_ei=$key SK_er=$key SK_pi=$key SK_pr=$key"
        val redacted = DiagnosticRedactor.redact(text)
        assertFalse(redacted.contains(key))
        assertEquals(11, Regex("\\[REDACTED_SECRET]").findAll(redacted).count())
        assertEquals("stage=IKEv2/IPsec result=Not tested", DiagnosticRedactor.redact("stage=IKEv2/IPsec result=Not tested"))
    }

    @Test fun byteArrayAndSpacedHexKeyLogsAreRemoved() {
        val redacted = DiagnosticRedactor.redact("CK=[0x01, 0x02, 0x03]\nIK: 01 02 03 04")
        assertFalse(redacted.contains("0x01"))
        assertFalse(redacted.contains("01 02"))
        assertEquals("CK=[REDACTED_SECRET]\nIK: [REDACTED_SECRET]", redacted)
    }
}

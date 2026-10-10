package com.nexvary.wificall.core

import kotlin.test.*

class CarrierEvidenceTest {
    private val carrier = CarrierKey("EG", "602", "01")
    private val device = "test-device"
    private fun record(outcome: EvidenceOutcome = EvidenceOutcome.VERIFIED) =
        EvidenceObservation(carrier, device, 1_700_000_000, outcome)
    private fun evidence(vararg stages: EvidenceStage) = CarrierEvidence(
        carrier, EvidenceLevel.UNKNOWN, device,
        observations = stages.associateWith { record() }
    )

    @Test fun mncIsPaddedForNaming() {
        val c = CarrierKey("EG", "602", "1")
        assertEquals("001", c.normalizedMnc)
        assertEquals("epdg.epc.mnc001.mcc602.pub.3gppnetwork.org", EpdgNaming.fqdn(c))
    }

    @Test fun summaryWithoutDatedScopedRecordsCannotVerifyVoice() {
        EvidenceLevel.entries.forEach { level ->
            assertFalse(CarrierEvidence(carrier, level, device).voiceVerified)
        }
    }

    @Test fun inboundDoesNotVerifyOutboundAudioOrIms() {
        val e = evidence(EvidenceStage.INBOUND_VERIFIED)
        assertTrue(e.inboundVerified)
        assertFalse(e.outboundVerified)
        assertFalse(e.audioVerified)
        assertFalse(e.imsRegistered)
        assertFalse(e.voiceVerified)
    }

    @Test fun outboundDoesNotVerifyInbound() {
        val e = evidence(EvidenceStage.OUTBOUND_VERIFIED)
        assertTrue(e.outboundVerified)
        assertFalse(e.inboundVerified)
        assertFalse(e.voiceVerified)
    }

    @Test fun bothDirectionsStillNeedIndependentAudioCheck() {
        val e = evidence(EvidenceStage.OUTBOUND_VERIFIED, EvidenceStage.INBOUND_VERIFIED)
        assertFalse(e.voiceVerified)
        assertTrue(evidence(EvidenceStage.OUTBOUND_VERIFIED, EvidenceStage.INBOUND_VERIFIED,
            EvidenceStage.AUDIO_VERIFIED).voiceVerified)
    }

    @Test fun failedObservationCannotVerifyStage() {
        val e = CarrierEvidence(carrier, EvidenceLevel.INBOUND_VOICE_VERIFIED, device,
            observations = mapOf(EvidenceStage.INBOUND_VERIFIED to record(EvidenceOutcome.FAILED)))
        assertFalse(e.inboundVerified)
    }

    @Test fun evidenceCannotBeReusedForAnotherDeviceOrCarrier() {
        val e = evidence(EvidenceStage.IMS_REGISTERED)
        assertFalse(e.isVerified(EvidenceStage.IMS_REGISTERED, "other-device"))
        assertFailsWith<IllegalArgumentException> {
            e.copy(carrier = CarrierKey("US", "310", "260"))
        }
        assertFailsWith<IllegalArgumentException> { e.copy(deviceScope = "other-device") }
    }

    @Test fun undatedOrUnscopedRecordsAreRejected() {
        assertFailsWith<IllegalArgumentException> { record().copy(checkedAtEpochSeconds = -1) }
        assertFailsWith<IllegalArgumentException> { record().copy(deviceScope = " ") }
        val unscoped = CarrierEvidence(carrier, EvidenceLevel.UNKNOWN,
            observations = mapOf(EvidenceStage.IMS_REGISTERED to record()))
        assertFalse(unscoped.imsRegistered)
        assertTrue(unscoped.isVerified(EvidenceStage.IMS_REGISTERED, device))
    }

    @Test fun simRankingDoesNotTreatInboundAsMoreCompleteThanOutbound() {
        val subscription = SubscriptionRef(1, 0, "Test", "602", "01", "EG")
        val outbound = SimPathCandidate(subscription, EvidenceLevel.OUTBOUND_VOICE_VERIFIED,
            ReadinessResult(ReadinessState.UNKNOWN))
        val inbound = outbound.copy(subscription = subscription.copy(id = 2, slotIndex = 1),
            evidence = EvidenceLevel.INBOUND_VOICE_VERIFIED)
        assertEquals(listOf(outbound, inbound), SimComparator.rank(listOf(outbound, inbound)))
        assertEquals(listOf(inbound, outbound), SimComparator.rank(listOf(inbound, outbound)))
    }
}

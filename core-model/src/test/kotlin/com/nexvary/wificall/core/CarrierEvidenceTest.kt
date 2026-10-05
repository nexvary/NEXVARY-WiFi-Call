package com.nexvary.wificall.core
import kotlin.test.*
class CarrierEvidenceTest {
 @Test fun mncIsPaddedForNaming(){ val c=CarrierKey("EG","602","1"); assertEquals("001",c.normalizedMnc); assertEquals("epdg.epc.mnc001.mcc602.pub.3gppnetwork.org",EpdgNaming.fqdn(c)) }
 @Test fun discoveryIsNotVoiceVerification(){ assertFalse(CarrierEvidence(CarrierKey("EG","602","01"),EvidenceLevel.DISCOVERED).voiceVerified) }
 @Test fun inboundVerificationPassesVoiceGate(){ assertTrue(CarrierEvidence(CarrierKey("EG","602","01"),EvidenceLevel.INBOUND_VOICE_VERIFIED).voiceVerified) }
}

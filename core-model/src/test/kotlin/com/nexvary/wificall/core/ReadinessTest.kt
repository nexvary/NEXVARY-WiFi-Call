package com.nexvary.wificall.core

import kotlin.test.*

class ReadinessTest {
    private val good = NetworkSnapshot(true, true, false, false)
    @Test fun captivePortalStopsEvaluation() {
        val r=ReadinessEngine.evaluate(ReadinessInput(NetworkSnapshot(true,false,true,false),true,false,true,false,false,true))
        assertEquals(ReadinessState.DEGRADED,r.state)
        assertTrue(Blocker.CAPTIVE_PORTAL in r.blockers)
    }
    @Test fun verifiedNativeWins() {
        val r=ReadinessEngine.evaluate(ReadinessInput(good,true,false,true,true,true,true))
        assertEquals(CallPath.NATIVE_CARRIER,r.path)
    }
    @Test fun restrictedIsNotUnsupported() {
        val r=ReadinessEngine.evaluate(ReadinessInput(good,true,true,false,false,false,true))
        assertEquals(ReadinessState.RESTRICTED,r.state)
    }
    @Test fun missingEvidenceStaysUnknown() {
        val r=ReadinessEngine.evaluate(ReadinessInput(good,true,false,false,false,false,false))
        assertEquals(ReadinessState.UNKNOWN,r.state)
    }
    @Test fun hiddenSubscriptionsAreNotReportedAsMissingSim() {
        val denied = ReadinessEngine.evaluate(ReadinessInput(good,false,true,false,false,false,false))
        assertEquals(ReadinessState.RESTRICTED, denied.state)
        assertEquals(setOf(Blocker.PLATFORM_RESTRICTED), denied.blockers)
        val noSelection = ReadinessEngine.evaluate(ReadinessInput(good,false,false,false,false,false,false))
        assertEquals(ReadinessState.UNKNOWN, noSelection.state)
        assertEquals(setOf(Blocker.SIM_NOT_SELECTED), noSelection.blockers)
    }
}

package com.nexvary.wificall.platform.gateway

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.nexvary.wificall.core.SubscriptionRef
import com.nexvary.wificall.platform.PhoneAsSimCapability
import com.nexvary.wificall.platform.PhoneAsSimProbeResult
import com.nexvary.wificall.ui.DemoState
import com.nexvary.wificall.ui.GatewayScreen
import com.nexvary.wificall.ui.NexvaryTheme
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.Test

/** The foreground broker must never be enabled merely because a device was paired. */
class PhoneAkaConsentTest {
    @get:Rule val compose = createComposeRule()
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    @Before fun pairedFixture() {
        GatewayPreferences(context).clear()
        GatewayPreferences(context).save(GatewayCredentials("https://gateway.example.org", "test-device",
            "0123456789_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"))
    }
    @After fun clean() { GatewayPreferences(context).clear() }
    private fun show(capability: PhoneAsSimCapability) {
        val state = DemoState.value.copy(subscriptions = listOf(SubscriptionRef(41, 0, "Carrier", null, null, null)),
            selectedSubscriptionId = 41, phoneAsSim = PhoneAsSimProbeResult(capability, 41, "Test fixture"))
        compose.setContent {
            NexvaryTheme { Column(Modifier.verticalScroll(rememberScrollState())) { GatewayScreen(state) } }
        }
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("aka-start").fetchSemanticsNodes().isNotEmpty() }
    }
    @Test fun verifiedPrivilegeStillRequiresExplicitConsent() {
        show(PhoneAsSimCapability.AVAILABLE_BY_CARRIER_PRIVILEGE)
        compose.onNodeWithTag("aka-start").performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag("aka-consent").performScrollTo().performClick()
        compose.onNodeWithTag("aka-start").assertIsEnabled()
        compose.onNodeWithTag("aka-stop").assertDoesNotExist()
    }
    @Test fun consentCannotOverrideMissingCarrierPrivileges() {
        show(PhoneAsSimCapability.CARRIER_PRIVILEGE_REQUIRED)
        compose.onNodeWithTag("aka-consent").performScrollTo().performClick()
        compose.onNodeWithTag("aka-start").assertIsNotEnabled()
        compose.onNodeWithTag("aka-stop").assertDoesNotExist()
    }
}

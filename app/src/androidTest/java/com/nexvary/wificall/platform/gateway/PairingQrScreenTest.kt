package com.nexvary.wificall.platform.gateway

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.*
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.nexvary.wificall.R
import com.nexvary.wificall.ui.DemoState
import com.nexvary.wificall.ui.GatewayScreen
import com.nexvary.wificall.ui.NexvaryTheme
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

class PairingQrScreenTest {
    @get:Rule val compose = createComposeRule()
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val code = "abcdefghijklmnopqrstuvwxyz_0123456789ABCDEFG"
    @Before fun cleanBefore() { GatewayPreferences(context).clear() }
    @After fun cleanAfter() { GatewayPreferences(context).clear() }

    private fun show(scanner: PairingQrScanner) {
        compose.setContent {
            NexvaryTheme {
                Column(Modifier.verticalScroll(rememberScrollState())) { GatewayScreen(DemoState.value, scanner) }
            }
        }
        compose.waitUntil(10_000) {
            val node = compose.onAllNodesWithTag("gateway-scan").fetchSemanticsNodes().firstOrNull()
            node != null && node.config.getOrNull(androidx.compose.ui.semantics.SemanticsProperties.Disabled) == null
        }
        compose.waitForIdle()
    }

    @Test fun scanningOnlyFillsFormAndStillRequiresExplicitPair() {
        val payload = JSONObject().put("type", "nexvary-pairing").put("version", 1)
            .put("url", "https://3.65.234.184:8443").put("code", code).toString()
        show(PairingQrScanner { PairingScanResult.Scanned(payload) })
        compose.onNodeWithTag("gateway-scan").performScrollTo().performClick()
        compose.onNodeWithTag("gateway-url").assertTextContains("https://3.65.234.184:8443")
        // Password fields expose masked editable text to accessibility/test semantics.
        // Verify that scanning filled it without exposing the pairing secret.
        compose.onNodeWithTag("gateway-code")
            .assertTextContains("\u2022".repeat(code.length))
            .assert(SemanticsMatcher.keyIsDefined(androidx.compose.ui.semantics.SemanticsProperties.Password))
        compose.onNodeWithTag("gateway-pair").assertIsEnabled()
        compose.onNodeWithTag("gateway-send").assertDoesNotExist()
        compose.onNodeWithTag("gateway-message").assertTextEquals(context.getString(R.string.gateway_qr_ready))
        assertTrue((GatewayPreferences(context).load() as GatewayResult.Success).value == null)
    }

    @Test fun unavailableScannerPreservesManualEntry() {
        show(PairingQrScanner { PairingScanResult.Unavailable })
        compose.onNodeWithTag("gateway-url").performTextInput("https://manual.example.org")
        compose.onNodeWithTag("gateway-scan").performScrollTo().performClick()
        compose.onNodeWithTag("gateway-url").assertTextContains("https://manual.example.org")
        compose.onNodeWithTag("gateway-message").assertTextEquals(context.getString(R.string.gateway_qr_unavailable))
        compose.onNodeWithTag("gateway-pair").assertIsEnabled()
    }

    @Test fun cancellationLeavesManualFormAndPairingStateUntouched() {
        show(PairingQrScanner { PairingScanResult.Cancelled })
        compose.onNodeWithTag("gateway-url").performTextInput("https://manual.example.org")
        compose.onNodeWithTag("gateway-scan").performScrollTo().performClick()
        compose.onNodeWithTag("gateway-url").assertTextContains("https://manual.example.org")
        compose.onNodeWithTag("gateway-pair").assertIsEnabled()
        compose.onNodeWithTag("gateway-message").assertDoesNotExist()
        compose.onNodeWithTag("gateway-send").assertDoesNotExist()
    }

    @Test fun malformedQrDoesNotReplaceManualFormOrCreateCredentials() {
        show(PairingQrScanner { PairingScanResult.Scanned("http://untrusted.example.org") })
        compose.onNodeWithTag("gateway-url").performTextInput("https://manual.example.org")
        compose.onNodeWithTag("gateway-scan").performScrollTo().performClick()
        compose.onNodeWithTag("gateway-url").assertTextContains("https://manual.example.org")
        compose.onNodeWithTag("gateway-message").assertTextEquals(context.getString(R.string.gateway_qr_invalid))
        compose.onNodeWithTag("gateway-send").assertDoesNotExist()
    }
}

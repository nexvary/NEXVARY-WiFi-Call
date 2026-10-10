package com.nexvary.wificall.ui

import android.content.res.Configuration
import android.os.LocaleList
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.LayoutDirection
import androidx.test.platform.app.InstrumentationRegistry
import com.nexvary.wificall.R
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized
import java.util.Locale

/** Offline validation must not send a request or manufacture a paired state. */
@RunWith(Parameterized::class)
class GatewayScreenTest(private val language: String) {
    @get:Rule val compose = createComposeRule()
    private val base = InstrumentationRegistry.getInstrumentation().targetContext

    @Before fun startUnpaired() { clearPairingFixture() }
    @After fun clearPairingFixture() {
        check(base.getSharedPreferences("gateway_credentials", 0).edit().clear().commit())
    }

    @Test fun localizedPairingValidationAndBack() {
        val locale = Locale.forLanguageTag(language)
        val context = base.createConfigurationContext(Configuration(base.resources.configuration).apply {
            setLocales(LocaleList(locale)); setLayoutDirection(locale); fontScale = 1.3f
        })
        fun text(id: Int) = context.getString(id)
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(
                LocalContext provides context,
                LocalDensity provides Density(density.density, fontScale = 1.3f),
                LocalLayoutDirection provides if (language == "ar") LayoutDirection.Rtl else LayoutDirection.Ltr
            ) { NexvaryTheme { WifiCallApp(initial = DemoState.value) } }
        }
        compose.onNodeWithTag("nav-settings").performClick()
        compose.onNodeWithText(text(R.string.gateway_title)).performScrollTo().performClick()
        compose.waitUntil(timeoutMillis = 10_000) {
            compose.onAllNodesWithTag("gateway-pair").fetchSemanticsNodes().singleOrNull()
                ?.config?.contains(SemanticsProperties.Disabled) == false
        }
        compose.onNodeWithTag("gateway-status").assertTextEquals(text(R.string.gateway_disconnected))
        compose.onNodeWithTag("gateway-send").assertDoesNotExist()
        compose.waitForIdle()
        Thread.sleep(300)
        ScreenshotFiles.capture("$language-gateway")

        compose.onNodeWithTag("gateway-url").performScrollTo().performTextInput("http://example.invalid")
        compose.onNodeWithTag("gateway-pair").performScrollTo().performClick()
        compose.onNodeWithTag("gateway-message").performScrollTo().assertTextEquals(text(R.string.gateway_error_url))
        compose.onNodeWithTag("gateway-status").assertTextEquals(text(R.string.gateway_disconnected))

        compose.onNodeWithTag("gateway-url").performScrollTo().performTextClearance()
        compose.onNodeWithTag("gateway-url").performTextInput("https://example.invalid")
        compose.onNodeWithTag("gateway-pair").performScrollTo().performClick()
        compose.onNodeWithTag("gateway-message").performScrollTo().assertTextEquals(text(R.string.gateway_code_required))
        compose.onNodeWithTag("gateway-send").assertDoesNotExist()
        compose.onNodeWithContentDescription(text(R.string.back)).performClick()
        compose.onNodeWithText(text(R.string.language)).performScrollTo().assertIsDisplayed()
    }

    companion object {
        @JvmStatic @Parameterized.Parameters(name = "{0}")
        fun languages() = listOf("ar", "en", "tr", "es", "de", "it", "fr")
    }
}

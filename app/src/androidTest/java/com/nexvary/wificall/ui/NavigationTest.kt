package com.nexvary.wificall.ui

import android.content.res.Configuration
import android.graphics.Bitmap
import android.os.LocaleList
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.Density
import androidx.test.platform.app.InstrumentationRegistry
import com.nexvary.wificall.R
import com.nexvary.wificall.core.SubscriptionRef
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized
import java.io.File
import java.util.Locale

@RunWith(Parameterized::class)
class NavigationTest(private val language: String) {
    @get:Rule val compose = createComposeRule()

    @Test fun localizedNavigationRefreshPermissionAndBack() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val base = instrumentation.targetContext
        val config = Configuration(base.resources.configuration).apply {
            setLocales(LocaleList(Locale.forLanguageTag(language)))
            setLayoutDirection(Locale.forLanguageTag(language))
            fontScale = 1.3f
        }
        val context = base.createConfigurationContext(config)
        fun text(id: Int) = context.getString(id)
        var refreshes = 0
        var permissions = 0
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(
                LocalContext provides context,
                LocalDensity provides Density(density.density, fontScale = 1.3f),
                LocalLayoutDirection provides if (language == "ar") LayoutDirection.Rtl else LayoutDirection.Ltr
            ) {
                NexvaryTheme {
                    WifiCallApp(initial = DemoState.value.copy(phonePermissionRequired = true), onRefresh = { refreshes++ }, onRequestPhonePermission = { permissions++ })
                }
            }
        }
        fun screenshot(name: String) {
            compose.waitForIdle()
            // Semantics settle before RenderThread commits the next display frame.
            // Allow the display and the card ripple to settle for visual review.
            Thread.sleep(300)
            val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
            val bitmap = checkNotNull(automation.takeScreenshot())
            val file = File(base.getExternalFilesDir("screenshots"), "$language-$name.png")
            file.parentFile!!.mkdirs()
            file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            fun shell(command: String) {
                val output = android.os.ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand(command))
                    .use { it.readBytes().toString(Charsets.UTF_8) }
                check(output.isBlank()) { output }
            }
            // executeShellCommand executes one program, not shell && operators.
            shell("mkdir -p /sdcard/Download/NEXVARY-WiFi-Call-screenshots")
            shell("cp ${file.absolutePath} /sdcard/Download/NEXVARY-WiFi-Call-screenshots/$language-$name.png")
        }
        compose.onNodeWithText(text(R.string.ready_title)).assertIsDisplayed()
        screenshot("home")
        compose.onNodeWithText(text(R.string.start_check)).performClick()
        compose.runOnIdle { assertEquals(1, refreshes) }
        compose.onNodeWithText(text(R.string.carrier_evidence)).performScrollTo().assertIsDisplayed()
        screenshot("diagnostics")
        compose.onNodeWithContentDescription(text(R.string.back)).performClick()
        compose.onNodeWithText(text(R.string.ready_title)).assertIsDisplayed()
        compose.onNodeWithText(text(R.string.sims)).performClick()
        compose.onNodeWithText(text(R.string.allow_sim)).performClick()
        compose.runOnIdle { assertEquals(1, permissions) }
        screenshot("sims")
        compose.onNodeWithText(text(R.string.more)).performClick()
        compose.onNodeWithText(text(R.string.about_developer)).performScrollTo().performClick()
        compose.onNodeWithText(text(R.string.about_description)).assertIsDisplayed()
        screenshot("about")
        compose.onNodeWithContentDescription(text(R.string.back)).performClick()
        compose.onNodeWithText(text(R.string.privacy)).performScrollTo().performClick()
        compose.onNodeWithText(text(R.string.privacy_secrets)).assertIsDisplayed()
        compose.onNodeWithContentDescription(text(R.string.back)).performClick()
        compose.onNodeWithText(text(R.string.language)).performScrollTo().assertIsDisplayed()
        screenshot("settings")
    }

    companion object {
        @JvmStatic @Parameterized.Parameters(name = "{0}") fun languages() = listOf("ar", "en", "tr", "es", "de", "it", "fr")
    }
}

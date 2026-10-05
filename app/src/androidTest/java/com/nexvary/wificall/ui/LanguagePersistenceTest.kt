package com.nexvary.wificall.ui

import android.graphics.Bitmap
import android.content.res.Configuration
import android.os.LocaleList
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.nexvary.wificall.MainActivity
import com.nexvary.wificall.R
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.Locale

/** Exercise the real activity locale/recreation path rather than a preview context. */
class LanguagePersistenceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val base = InstrumentationRegistry.getInstrumentation().targetContext

    @After fun resetLanguage() {
        base.getSharedPreferences("preferences", 0).edit().remove("language").commit()
    }

    @Test fun languageSwitchSurvivesActivityRecreation() {
        fun translated(language: String, id: Int): String {
            val config = Configuration(base.resources.configuration).apply { setLocales(LocaleList(Locale.forLanguageTag(language))) }
            return base.createConfigurationContext(config).getString(id)
        }
        var language = base.getSharedPreferences("preferences", 0).getString("language", "").orEmpty().ifEmpty {
            base.resources.configuration.locales[0].language
        }
        compose.onNodeWithText(translated(language, R.string.more)).performClick()
        val options = listOf("ar" to "العربية", "en" to "English", "tr" to "Türkçe", "es" to "Español", "de" to "Deutsch", "it" to "Italiano", "fr" to "Français")
        options.forEach { (code, name) ->
            val current = compose.activity.getSharedPreferences("preferences", 0).getString("language", "").orEmpty()
            val selectedName = options.firstOrNull { it.first == current }?.second ?: translated(language, R.string.follow_system)
            compose.onNodeWithText(selectedName).performScrollTo().performClick()
            compose.onNodeWithText(name).performClick()
            compose.waitUntil(timeoutMillis = 10_000) {
                compose.onAllNodesWithText(translated(code, R.string.more)).fetchSemanticsNodes().isNotEmpty()
            }
            compose.onNodeWithText(translated(code, R.string.language)).performScrollTo().assertIsDisplayed()
            compose.activityRule.scenario.recreate()
            compose.onNodeWithText(translated(code, R.string.more)).assertIsDisplayed()
            assertEquals(
                if (code == "ar") android.view.View.LAYOUT_DIRECTION_RTL else android.view.View.LAYOUT_DIRECTION_LTR,
                compose.activity.resources.configuration.layoutDirection
            )
            language = code
            if (code == "ar" || code == "en") {
                compose.onNodeWithText(translated(code, R.string.home)).performClick()
                compose.waitForIdle()
                Thread.sleep(300)
                val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
                val bitmap = checkNotNull(automation.takeScreenshot())
                val file = File(base.getExternalFilesDir("screenshots"), "$code-activity-home.png")
                file.parentFile!!.mkdirs()
                file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
                fun shell(command: String) {
                    val output = android.os.ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand(command))
                        .use { it.readBytes().toString(Charsets.UTF_8) }
                    check(output.isBlank()) { output }
                }
                // executeShellCommand executes one program, not shell && operators.
                shell("mkdir -p /sdcard/Download/NEXVARY-WiFi-Call-screenshots")
                shell("cp ${file.absolutePath} /sdcard/Download/NEXVARY-WiFi-Call-screenshots/$code-activity-home.png")
                compose.onNodeWithText(translated(code, R.string.more)).performClick()
            }
        }
        val selectedName = options.first { it.first == language }.second
        compose.onNodeWithText(selectedName).performScrollTo().performClick()
        compose.onNodeWithText(translated(language, R.string.follow_system)).performClick()
        val deviceLanguage = base.resources.configuration.locales[0].language
        compose.waitUntil(timeoutMillis = 10_000) {
            compose.onAllNodesWithText(translated(deviceLanguage, R.string.more)).fetchSemanticsNodes().isNotEmpty()
        }
        compose.activityRule.scenario.recreate()
        compose.onNodeWithText(translated(deviceLanguage, R.string.more)).assertIsDisplayed()
        assertEquals("", compose.activity.getSharedPreferences("preferences", 0).getString("language", ""))
    }
}

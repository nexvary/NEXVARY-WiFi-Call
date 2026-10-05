package com.nexvary.wificall.ui

import android.app.Activity
import android.app.Instrumentation
import android.content.Intent
import android.content.ComponentName
import android.content.pm.ActivityInfo
import android.content.pm.LauncherApps
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.drawable.AdaptiveIconDrawable
import android.os.Process
import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.test.platform.app.InstrumentationRegistry
import com.nexvary.wificall.MainActivity
import com.nexvary.wificall.R
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.concurrent.atomic.AtomicReference

/** Checks installed package resources and activity behavior, rather than source-file presence. */
class DeviceContractTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test fun installedLauncherResolvesBrandedAdaptiveIcon() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val launchIntent = checkNotNull(context.packageManager.getLaunchIntentForPackage(context.packageName))
        assertEquals(ComponentName(context, MainActivity::class.java), launchIntent.component)
        val launcher = checkNotNull(context.getSystemService(LauncherApps::class.java))
        val entry = launcher.getActivityList(context.packageName, Process.myUserHandle()).single()
        assertEquals(launchIntent.component, entry.componentName)
        val icon = entry.getIcon(context.resources.displayMetrics.densityDpi)
        assertTrue("Installed launcher must use an adaptive app icon", icon is AdaptiveIconDrawable)
        val info = context.packageManager.getApplicationInfo(context.packageName, 0)
        assertTrue("App icon must not use the default system icon", info.icon != 0 && info.icon != android.R.drawable.sym_def_app_icon)
        val bitmap = Bitmap.createBitmap(256, 256, Bitmap.Config.ARGB_8888)
        icon.setBounds(0, 0, 256, 256)
        icon.draw(Canvas(bitmap))
        ScreenshotFiles.save(bitmap, "installed-launcher-icon")
        launcher.startMainActivity(entry.componentName, Process.myUserHandle(), null, null)
        compose.onNodeWithText(compose.activity.getString(R.string.ready_title)).assertIsDisplayed()
    }

    @Test fun developerLinksLaunchExpectedExternalIntents() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val lastIntent = AtomicReference<Intent?>(null)
        val monitor = object : Instrumentation.ActivityMonitor() {
            override fun onStartActivity(intent: Intent): Instrumentation.ActivityResult? {
                if (intent.action == Intent.ACTION_VIEW || intent.action == Intent.ACTION_SENDTO) {
                    lastIntent.set(Intent(intent))
                    return Instrumentation.ActivityResult(Activity.RESULT_CANCELED, null)
                }
                return null
            }
        }
        instrumentation.addMonitor(monitor)
        try {
            fun text(id: Int) = compose.activity.getString(id)
            compose.onNodeWithTag("nav-settings").performClick()
            compose.onNodeWithText(text(R.string.about_developer)).performScrollTo().performClick()
            listOf(
                R.string.official_website to "https://fgmachines.org",
                R.string.email to "mailto:info@fgmachines.org",
                R.string.business_page to "https://www.facebook.com/share/1T7r3WpH8Y/",
                R.string.personal_page to "https://www.facebook.com/share/1EKVAyZZ2C/"
            ).forEach { (label, expected) ->
                lastIntent.set(null)
                compose.onNodeWithText(text(label)).performScrollTo().performClick()
                compose.waitForIdle()
                assertEquals(expected, lastIntent.get()?.dataString)
            }
        } finally {
            instrumentation.removeMonitor(monitor)
        }
    }

    @Test fun dashboardSurvivesLandscapeAndPortrait() {
        try {
            compose.activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            compose.waitUntil(15_000) {
                compose.activity.resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
            }
            compose.onNodeWithText(compose.activity.getString(R.string.start_check)).performScrollTo().assertIsDisplayed()
            compose.waitForIdle()
            Thread.sleep(300)
            ScreenshotFiles.capture("activity-landscape")
            compose.activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
            compose.waitUntil(15_000) {
                compose.activity.resources.configuration.orientation == Configuration.ORIENTATION_PORTRAIT
            }
            compose.onNodeWithText(compose.activity.getString(R.string.ready_title)).performScrollTo().assertIsDisplayed()
            compose.waitForIdle()
            Thread.sleep(300)
            ScreenshotFiles.capture("activity-portrait")
        } finally {
            compose.activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        }
    }
}

internal object ScreenshotFiles {
    fun capture(name: String) = save(checkNotNull(InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()), name)
    fun save(bitmap: Bitmap, name: String) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val file = File(instrumentation.targetContext.getExternalFilesDir("screenshots"), "$name.png")
        file.parentFile!!.mkdirs()
        file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        fun shell(command: String) {
            val output = ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(command))
                .use { it.readBytes().toString(Charsets.UTF_8) }
            check(output.isBlank()) { output }
        }
        shell("mkdir -p /sdcard/Download/NEXVARY-WiFi-Call-screenshots")
        shell("cp ${file.absolutePath} /sdcard/Download/NEXVARY-WiFi-Call-screenshots/$name.png")
    }
}

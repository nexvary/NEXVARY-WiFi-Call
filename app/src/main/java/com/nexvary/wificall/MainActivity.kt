package com.nexvary.wificall

import android.Manifest
import android.content.Context
import android.content.res.Configuration
import android.os.Bundle
import android.os.LocaleList
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.SystemBarStyle
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.nexvary.wificall.ui.DashboardLoader
import com.nexvary.wificall.ui.NexvaryTheme
import com.nexvary.wificall.ui.WifiCallApp
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun attachBaseContext(newBase: Context) {
        val language = newBase.getSharedPreferences("preferences", MODE_PRIVATE).getString("language", "").orEmpty()
        val context = if (language.isEmpty()) newBase else {
            val configuration = Configuration(newBase.resources.configuration)
            val locale = Locale.forLanguageTag(language)
            configuration.setLocales(LocaleList(locale))
            configuration.setLayoutDirection(locale)
            newBase.createConfigurationContext(configuration)
        }
        super.attachBaseContext(context)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(statusBarStyle = SystemBarStyle.dark(0xFF071018.toInt()), navigationBarStyle = SystemBarStyle.dark(0xFF071018.toInt()))
        setContent {
            NexvaryTheme {
                val context = LocalContext.current
                var refresh by remember { mutableIntStateOf(0) }
                var selectedSubscription by remember { mutableStateOf<Int?>(null) }
                val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { refresh++ }
                val state = remember(refresh, selectedSubscription) { DashboardLoader.load(context, selectedSubscription) }
                DisposableEffect(Unit) {
                    val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) refresh++ }
                    lifecycle.addObserver(observer)
                    onDispose { lifecycle.removeObserver(observer) }
                }
                WifiCallApp(
                    initial = state,
                    onRequestPhonePermission = { permission.launch(Manifest.permission.READ_PHONE_STATE) },
                    onRefresh = { refresh++ },
                    language = getSharedPreferences("preferences", MODE_PRIVATE).getString("language", "").orEmpty(),
                    onLanguageChange = { language ->
                        getSharedPreferences("preferences", MODE_PRIVATE).edit().putString("language", language).apply()
                        recreate()
                    },
                    onSelectSubscription = { selectedSubscription = it }
                )
            }
        }
    }
}

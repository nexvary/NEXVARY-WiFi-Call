package com.nexvary.wificall

import android.Manifest
import android.app.LocaleManager
import android.content.Context
import android.content.res.Configuration
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.LocaleList
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.SystemBarStyle
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.nexvary.wificall.ui.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun attachBaseContext(newBase: Context) {
        // Android 13+ owns persistence, recreation and system Settings integration.
        // Older versions retain the localized-context fallback without global locale mutation.
        val language = newBase.getSharedPreferences("preferences", MODE_PRIVATE).getString("language", "").orEmpty()
        val context = if (Build.VERSION.SDK_INT >= 33 || language.isEmpty()) newBase else {
            val configuration = Configuration(newBase.resources.configuration)
            val locale = Locale.forLanguageTag(language)
            configuration.setLocales(LocaleList(locale))
            configuration.setLayoutDirection(locale)
            newBase.createConfigurationContext(configuration)
        }
        super.attachBaseContext(context)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        val preferences = getSharedPreferences("preferences", MODE_PRIVATE)
        if (Build.VERSION.SDK_INT >= 33 && !preferences.getBoolean("framework_locale_migrated", false)) {
            val manager = getSystemService(LocaleManager::class.java)
            val legacy = preferences.getString("language", "").orEmpty()
            if (manager.applicationLocales.isEmpty && legacy.isNotEmpty()) {
                manager.applicationLocales = LocaleList.forLanguageTags(legacy)
            }
            preferences.edit().putBoolean("framework_locale_migrated", true).apply()
        }
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(statusBarStyle = SystemBarStyle.dark(0xFF071018.toInt()), navigationBarStyle = SystemBarStyle.dark(0xFF071018.toInt()))
        if (Build.VERSION.SDK_INT >= 29) window.isNavigationBarContrastEnforced = false
        setContent {
            NexvaryTheme {
                val context = LocalContext.current
                var refresh by remember { mutableIntStateOf(0) }
                var selectedSubscription by rememberSaveable {
                    mutableStateOf(preferences.getInt("selected_subscription", -1).takeIf { it >= 0 })
                }
                var state by remember { mutableStateOf(DemoState.value.copy(checking = true)) }
                LaunchedEffect(refresh, selectedSubscription) {
                    state = state.copy(checking = true)
                    val loaded = withContext(Dispatchers.IO) { DashboardLoader.load(context, selectedSubscription) }
                    val savedMode = if (preferences.getString("mode", "consumer") == "lab") AppMode.LAB else AppMode.CONSUMER
                    state = loaded.copy(mode = savedMode)
                }
                val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { refresh++ }
                DisposableEffect(Unit) {
                    val cm = context.getSystemService(ConnectivityManager::class.java)
                    val handler = Handler(Looper.getMainLooper())
                    var registered = false
                    var active = false
                    val callback = object : ConnectivityManager.NetworkCallback() {
                        private fun changed() { handler.post { if (active) refresh++ } }
                        override fun onAvailable(network: Network) = changed()
                        override fun onLost(network: Network) = changed()
                        override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) = changed()
                    }
                    fun start() {
                        active = true
                        if (!registered && cm != null) {
                            try {
                                cm.registerDefaultNetworkCallback(callback)
                                registered = true
                            } catch (_: SecurityException) {
                                // Snapshot remains available; never report registration as connectivity evidence.
                            } catch (_: RuntimeException) {
                                // A temporary platform failure must not crash the activity.
                            }
                        }
                        refresh++
                    }
                    fun stop() {
                        active = false
                        if (registered) {
                            try { cm?.unregisterNetworkCallback(callback) } catch (_: RuntimeException) { }
                            registered = false
                        }
                    }
                    val observer = LifecycleEventObserver { _, event ->
                        when (event) {
                            Lifecycle.Event.ON_START -> start()
                            Lifecycle.Event.ON_STOP -> stop()
                            else -> Unit
                        }
                    }
                    lifecycle.addObserver(observer)
                    if (lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) start()
                    onDispose {
                        stop()
                        lifecycle.removeObserver(observer)
                    }
                }
                val language = if (Build.VERSION.SDK_INT >= 33) {
                    getSystemService(LocaleManager::class.java).applicationLocales.toLanguageTags()
                } else preferences.getString("language", "").orEmpty()
                WifiCallApp(
                    initial = state,
                    onRequestPhonePermission = { permission.launch(Manifest.permission.READ_PHONE_STATE) },
                    onRefresh = { refresh++ },
                    language = language,
                    onLanguageChange = { chosen ->
                        preferences.edit().putString("language", chosen).apply()
                        if (Build.VERSION.SDK_INT >= 33) {
                            getSystemService(LocaleManager::class.java).applicationLocales = LocaleList.forLanguageTags(chosen)
                        } else recreate()
                    },
                    onModeChange = { mode ->
                        preferences.edit().putString("mode", if (mode == AppMode.LAB) "lab" else "consumer").apply()
                    },
                    onSelectSubscription = {
                        preferences.edit().putInt("selected_subscription", it).apply()
                        selectedSubscription = it
                    }
                )
            }
        }
    }
}

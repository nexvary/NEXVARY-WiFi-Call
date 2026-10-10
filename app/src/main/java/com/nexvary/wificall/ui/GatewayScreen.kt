package com.nexvary.wificall.ui

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.SystemClock
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudSync
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.PrivacyTip
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.unit.dp
import com.nexvary.wificall.R
import com.nexvary.wificall.platform.gateway.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.LifecycleOwner
import com.nexvary.wificall.platform.PhoneAsSimCapability
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Pairing and reporting are explicit user actions, unrelated to carrier authentication. */
@Composable fun GatewayScreen(state: DashboardState, scanner: PairingQrScanner = GooglePairingQrScanner) {
    val scanContext = LocalContext.current
    val context = LocalContext.current.applicationContext
    val preferences = remember(context) { GatewayPreferences(context) }
    val client = remember { GatewayClient() }
    val scope = rememberCoroutineScope()
    var credentials by remember { mutableStateOf<GatewayCredentials?>(null) }
    var url by remember { mutableStateOf("") }
    // Pairing codes and bearer credentials must not enter saved instance state.
    var code by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(true) }
    var busyAction by remember { mutableStateOf<Int?>(null) }
    var message by remember { mutableStateOf<Int?>(null) }
    var error by remember { mutableStateOf(false) }
    var remotelyRevoked by remember { mutableStateOf(false) }
    var akaConsent by remember { mutableStateOf(false) }
    var akaRunning by remember { mutableStateOf(false) }
    var akaJob by remember { mutableStateOf<Job?>(null) }
    val latestState by rememberUpdatedState(state)
    val akaClient = remember { PhoneAkaClient() }
    val akaAdapter = remember(context) { PhoneAkaAdapter(context) }
    val busy = loading || busyAction != null || akaRunning

    DisposableEffect(scanContext, state.selectedSubscriptionId, credentials?.deviceId) {
        val owner = scanContext as? LifecycleOwner
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) akaJob?.cancel()
        }
        owner?.lifecycle?.addObserver(observer)
        onDispose {
            akaJob?.cancel()
            akaConsent = false
            owner?.lifecycle?.removeObserver(observer)
        }
    }

    LaunchedEffect(preferences) {
        when (val loaded = withContext(Dispatchers.IO) { preferences.load() }) {
            is GatewayResult.Success -> { credentials = loaded.value; url = loaded.value?.baseUrl.orEmpty() }
            is GatewayResult.Failure -> { message = R.string.gateway_error_storage; error = true }
        }
        loading = false
    }

    fun showMessage(resource: Int, failure: Boolean = false) { message = resource; error = failure }
    fun foreground() = (scanContext as? LifecycleOwner)?.lifecycle?.currentState
        ?.isAtLeast(Lifecycle.State.STARTED) == true
    fun startAka() {
        val paired = credentials ?: return
        val selected = state.subscriptions.firstOrNull { it.id == state.selectedSubscriptionId } ?: return
        if (busy || !foreground() || !akaConsent || remotelyRevoked || selected.slotIndex !in 0..7 ||
            state.phoneAsSim?.capability != PhoneAsSimCapability.AVAILABLE_BY_CARRIER_PRIVILEGE) return
        akaRunning = true
        message = R.string.aka_starting
        error = false
        akaJob = scope.launch {
            var opened: PhoneAkaSession? = null
            try {
                val started = withContext(Dispatchers.IO) {
                    akaClient.start(paired, selected.slotIndex).also {
                        if (it is GatewayResult.Success) opened = it.value
                    }
                }
                if (started is GatewayResult.Failure) { showMessage(R.string.aka_error, true); return@launch }
                val session = (started as GatewayResult.Success).value
                val deadline = SystemClock.elapsedRealtime() + 300_000
                showMessage(R.string.aka_active)
                while (isActive && foreground() && SystemClock.elapsedRealtime() < deadline &&
                    System.currentTimeMillis() / 1000 < session.expiresAt) {
                    if (latestState.selectedSubscriptionId != selected.id) break
                    val polled = withContext(Dispatchers.IO) { akaClient.poll(paired, session) }
                    if (polled is GatewayResult.Failure) { showMessage(R.string.aka_error, true); break }
                    val challenge = (polled as GatewayResult.Success).value
                    if (challenge != null) {
                        val handled = withContext(Dispatchers.IO) {
                            if (!isActive || !foreground() || latestState.selectedSubscriptionId != selected.id ||
                                System.currentTimeMillis() / 1000 >= challenge.expiresAt) null else {
                                val response = akaAdapter.authenticate(selected.id, challenge.rand, challenge.autn)
                                try {
                                    if (!isActive || !foreground() || latestState.selectedSubscriptionId != selected.id ||
                                        System.currentTimeMillis() / 1000 >= challenge.expiresAt) null else {
                                        val submitted = akaClient.submit(paired, session, challenge, response)
                                        Pair(submitted, when (response) {
                                            is PhoneAkaResult.Success -> R.string.aka_response_sent
                                            is PhoneAkaResult.SynchronizationFailure -> R.string.aka_sync_sent
                                            is PhoneAkaResult.Failure -> R.string.aka_unavailable
                                        })
                                    }
                                } finally { response.destroy() }
                            }
                        }
                        if (handled == null) break
                        if (handled.first is GatewayResult.Failure) { showMessage(R.string.aka_error, true); break }
                        showMessage(handled.second, handled.second == R.string.aka_unavailable)
                        if (handled.second == R.string.aka_unavailable) break
                    }
                    delay(2_000)
                }
            } catch (_: CancellationException) {
                // Leaving the foreground never starts or continues authentication.
            } finally {
                opened?.let { session -> withContext(NonCancellable + Dispatchers.IO) { akaClient.stop(paired, session) } }
                akaRunning = false
                akaConsent = false
                if (!error) showMessage(R.string.aka_stopped)
                akaJob = null
            }
        }
    }
    fun stopAka() { akaJob?.cancel() }
    fun scan() {
        if (loading || busyAction != null || credentials != null) return
        busyAction = R.string.gateway_qr_scanning
        message = null
        scope.launch {
            try {
                when (val result = scanner.scan(scanContext)) {
                    is PairingScanResult.Scanned -> {
                        val candidate = PairingQrParser.parse(result.raw)
                        if (candidate == null) showMessage(R.string.gateway_qr_invalid, true)
                        else {
                            url = candidate.url
                            code = candidate.code
                            showMessage(R.string.gateway_qr_ready)
                        }
                    }
                    PairingScanResult.Unavailable -> showMessage(R.string.gateway_qr_unavailable, true)
                    PairingScanResult.Cancelled -> Unit
                }
            } finally { busyAction = null }
        }
    }
    fun pair() {
        if (loading || busyAction != null || akaRunning) return
        if (GatewayAddress.normalize(url) == null) { showMessage(R.string.gateway_error_url, true); return }
        if (code.isBlank()) { showMessage(R.string.gateway_code_required, true); return }
        busyAction = R.string.gateway_pairing
        message = null
        val requestedUrl = url.trim()
        val requestedCode = code.trim()
        scope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    when (val paired = client.pair(requestedUrl, requestedCode)) {
                        is GatewayResult.Failure -> paired
                        is GatewayResult.Success -> when (val saved = preferences.save(paired.value)) {
                            is GatewayResult.Success -> paired
                            is GatewayResult.Failure -> {
                                // Best-effort revoke if local secure storage failed.
                                client.disconnect(paired.value)
                                saved
                            }
                        }
                    }
                }
                code = ""
                when (result) {
                    is GatewayResult.Success -> { credentials = result.value; remotelyRevoked = false; url = result.value.baseUrl; showMessage(R.string.gateway_paired) }
                    is GatewayResult.Failure -> showMessage(when (result.error) {
                        GatewayError.INVALID_URL -> R.string.gateway_error_url
                        GatewayError.INVALID_CODE -> R.string.gateway_invalid_code
                        GatewayError.STORAGE -> R.string.gateway_error_storage
                        else -> R.string.gateway_error_pair
                    }, true)
                }
            } finally { busyAction = null }
        }
    }
    fun send() {
        val paired = credentials ?: return
        if (loading || busyAction != null || remotelyRevoked) return
        busyAction = R.string.gateway_sending
        message = null
        scope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    client.report(paired, GatewayReport(
                        simCount = state.subscriptions.size,
                        selectedSlot = state.subscriptions.firstOrNull { it.id == state.selectedSubscriptionId }?.slotIndex?.takeIf { it in 0..7 },
                        network = currentGatewayNetwork(context),
                        phoneAsSim = state.phoneAsSim?.capability,
                        androidApi = Build.VERSION.SDK_INT
                    ))
                }
                when (result) {
                    is GatewayResult.Success -> {
                        withContext(Dispatchers.IO) { preferences.recordReportSuccess(System.currentTimeMillis()) }
                        showMessage(R.string.gateway_sent)
                    }
                    is GatewayResult.Failure -> showMessage(R.string.gateway_error_send, true)
                }
            } finally { busyAction = null }
        }
    }
    fun disconnect() {
        val paired = credentials ?: return
        if (loading || busyAction != null || akaRunning) return
        busyAction = R.string.gateway_disconnecting
        message = null
        scope.launch {
            try {
                val revoked = if (remotelyRevoked) GatewayResult.Success(Unit) else withContext(Dispatchers.IO) { client.disconnect(paired) }
                val result = when (revoked) {
                    is GatewayResult.Failure -> if (revoked.error == GatewayError.UNAUTHORIZED) {
                        // A revoked/expired credential can be removed without another successful request.
                        remotelyRevoked = true
                        withContext(Dispatchers.IO) { preferences.clear() }
                    } else revoked
                    is GatewayResult.Success -> {
                        remotelyRevoked = true
                        withContext(Dispatchers.IO) { preferences.clear() }
                    }
                }
                when (result) {
                    is GatewayResult.Success -> { credentials = null; code = ""; showMessage(R.string.gateway_disconnected) }
                    is GatewayResult.Failure -> showMessage(if (result.error == GatewayError.STORAGE) R.string.gateway_error_storage else R.string.gateway_error_disconnect, true)
                }
            } finally { busyAction = null }
        }
    }

    Column(Modifier.fillMaxWidth().imePadding(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Icon(Icons.Default.Link, null, tint = MaterialTheme.colorScheme.primary)
                Text(stringResource(if (credentials == null) R.string.gateway_disconnected else R.string.gateway_paired), style = MaterialTheme.typography.titleMedium, modifier = Modifier.testTag("gateway-status"))
            }
            Text(stringResource(R.string.gateway_intro), style = MaterialTheme.typography.bodyMedium)
            credentials?.let { Text(it.baseUrl, style = MaterialTheme.typography.bodyMedium.copy(textDirection = TextDirection.Ltr), color = MaterialTheme.colorScheme.primary) }
        } }
        if (credentials == null) {
            Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = ::scan, enabled = !busy,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("gateway-scan")) {
                    Icon(Icons.Default.QrCodeScanner, null)
                    Spacer(Modifier.width(8.dp))
                    Text(stringResource(R.string.gateway_scan_qr))
                }
                OutlinedTextField(url, onValueChange = { url = it.take(2048) }, enabled = !busy,
                    label = { Text(stringResource(R.string.gateway_url)) }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    textStyle = MaterialTheme.typography.bodyLarge.copy(textDirection = TextDirection.Ltr),
                    modifier = Modifier.fillMaxWidth().testTag("gateway-url"))
                OutlinedTextField(code, onValueChange = { code = it.take(128) }, enabled = !busy,
                    label = { Text(stringResource(R.string.gateway_code)) }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    visualTransformation = PasswordVisualTransformation(),
                    textStyle = MaterialTheme.typography.bodyLarge.copy(textDirection = TextDirection.Ltr),
                    modifier = Modifier.fillMaxWidth().testTag("gateway-code"))
                Button(onClick = ::pair, enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("gateway-pair")) {
                    Icon(Icons.Default.CloudSync, null); Spacer(Modifier.width(8.dp)); Text(stringResource(R.string.gateway_pair))
                }
            } }
        } else {
            Button(onClick = ::send, enabled = !busy && !remotelyRevoked, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("gateway-send")) { Text(stringResource(R.string.gateway_send)) }
            OutlinedButton(onClick = ::disconnect, enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("gateway-disconnect")) { Text(stringResource(R.string.gateway_disconnect)) }
        }
        if (credentials != null) {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(stringResource(R.string.aka_title), style = MaterialTheme.typography.titleMedium)
                    Text(stringResource(R.string.aka_consent), style = MaterialTheme.typography.bodySmall)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = akaConsent, onCheckedChange = { akaConsent = it }, enabled = !busy,
                            modifier = Modifier.testTag("aka-consent"))
                        Text(stringResource(R.string.aka_enable), style = MaterialTheme.typography.bodyMedium)
                    }
                    val available = state.selectedSubscriptionId != null &&
                        state.phoneAsSim?.capability == PhoneAsSimCapability.AVAILABLE_BY_CARRIER_PRIVILEGE
                    if (!available) Text(stringResource(R.string.aka_unavailable), color = MaterialTheme.colorScheme.secondary,
                        style = MaterialTheme.typography.bodySmall)
                    if (akaRunning) OutlinedButton(onClick = ::stopAka, modifier = Modifier.fillMaxWidth().testTag("aka-stop")) {
                        Text(stringResource(R.string.aka_stop))
                    } else Button(onClick = ::startAka, enabled = !busy && akaConsent && available && !remotelyRevoked,
                        modifier = Modifier.fillMaxWidth().testTag("aka-start")) { Text(stringResource(R.string.aka_start)) }
                }
            }
        }
        if (busy) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
            busyAction?.let { Text(stringResource(it), style = MaterialTheme.typography.bodyMedium) }
        }
        message?.let { Text(stringResource(it), color = if (error) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.testTag("gateway-message")) }
        Card(Modifier.fillMaxWidth()) { Row(Modifier.padding(16.dp), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Icon(Icons.Default.PrivacyTip, null, tint = MaterialTheme.colorScheme.primary)
            Text(stringResource(R.string.gateway_privacy), style = MaterialTheme.typography.bodySmall)
        } }
    }
}

private fun currentGatewayNetwork(context: Context): GatewayNetwork = try {
    val manager = context.getSystemService(ConnectivityManager::class.java)
    val active = manager?.activeNetwork
    if (manager == null) GatewayNetwork.UNKNOWN else if (active == null) GatewayNetwork.NONE else {
        val capabilities = manager.getNetworkCapabilities(active)
        when {
            capabilities == null -> GatewayNetwork.UNKNOWN
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> GatewayNetwork.WIFI
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> GatewayNetwork.CELLULAR
            else -> GatewayNetwork.OTHER
        }
    }
} catch (_: RuntimeException) { GatewayNetwork.UNKNOWN }

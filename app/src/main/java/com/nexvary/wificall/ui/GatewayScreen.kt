package com.nexvary.wificall.ui

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudSync
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.PrivacyTip
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
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Pairing and reporting are explicit user actions, unrelated to carrier authentication. */
@Composable fun GatewayScreen(state: DashboardState) {
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
    val busy = loading || busyAction != null

    LaunchedEffect(preferences) {
        when (val loaded = withContext(Dispatchers.IO) { preferences.load() }) {
            is GatewayResult.Success -> { credentials = loaded.value; url = loaded.value?.baseUrl.orEmpty() }
            is GatewayResult.Failure -> { message = R.string.gateway_error_storage; error = true }
        }
        loading = false
    }

    fun showMessage(resource: Int, failure: Boolean = false) { message = resource; error = failure }
    fun pair() {
        if (loading || busyAction != null) return
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
        if (loading || busyAction != null) return
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

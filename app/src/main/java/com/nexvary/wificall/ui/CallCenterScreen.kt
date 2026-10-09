package com.nexvary.wificall.ui

import android.app.Activity
import android.content.Intent
import android.provider.ContactsContract
import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.nexvary.wificall.R
import com.nexvary.wificall.core.*
import com.nexvary.wificall.platform.PhoneAsSimCapability
import com.nexvary.wificall.platform.sip.*

@Composable
fun CallCenterScreen(client: SipClient, dashboard: DashboardState) {
    val state by client.state.collectAsState()
    val context = LocalContext.current
    var selected by rememberSaveable { mutableStateOf(CallingRoute.SIP_INTERNAL) }
    var host by rememberSaveable { mutableStateOf("") }
    var port by rememberSaveable { mutableStateOf("5061") }
    var user by rememberSaveable { mutableStateOf("1001") }
    var password by remember { mutableStateOf("") }
    var target by rememberSaveable { mutableStateOf("1002") }
    var stun by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    fun register() {
        try { client.register(host.trim(), port.toIntOrNull() ?: 0, user.trim(), password, stun.trim()); error = null }
        catch (_: Exception) { error = context.getString(R.string.sip_setup_error) }
        finally { password = "" }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { results ->
        if (results[Manifest.permission.RECORD_AUDIO] == true) register()
        else { password = ""; error = context.getString(R.string.sip_permission_required) }
    }
    val contacts = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val uri = result.data?.data
            try {
                val number = uri?.let { context.contentResolver.query(it, arrayOf(ContactsContract.CommonDataKinds.Phone.NUMBER), null, null, null)?.use { cursor ->
                    if (cursor.moveToFirst()) cursor.getString(0) else null
                } }.orEmpty().replace(" ", "").replace("-", "")
                if (InternalDialPolicy.validExtension(number)) { target = number; error = null }
                else error = context.getString(R.string.sip_contact_internal_only)
            } catch (_: Exception) { error = context.getString(R.string.sip_contact_error) }
        }
    }
    val busy = state.call !in setOf(SipCallPhase.IDLE, SipCallPhase.FAILED)
    LaunchedEffect(state.call) { if (state.call == SipCallPhase.INCOMING) selected = CallingRoute.SIP_INTERNAL }
    Text(stringResource(R.string.call_center_description), style = MaterialTheme.typography.bodyMedium)
    if (busy) {
        Card(Modifier.fillMaxWidth().testTag("sip-active-call")) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.sip_call_state, state.peer, stringResource(when (state.call) { SipCallPhase.INCOMING -> R.string.sip_incoming; SipCallPhase.DIALLING -> R.string.sip_phase_dialling; SipCallPhase.RINGING -> R.string.sip_phase_ringing; SipCallPhase.CONNECTED -> R.string.sip_phase_connected; SipCallPhase.MEDIA_ACTIVE -> R.string.sip_phase_media; SipCallPhase.FAILED -> R.string.sip_call_error; else -> R.string.sip_offline })))
                if (state.call == SipCallPhase.INCOMING) Button(onClick = { try { client.answer() } catch (_: Exception) { error = context.getString(R.string.sip_call_error) } }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.sip_answer)) }
                Button(onClick = { client.hangUp() }, colors = ButtonDefaults.buttonColors(containerColor = ErrorColor), modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.sip_hangup)) }
                OutlinedButton(onClick = { client.toggleMute() }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(if (state.muted) R.string.sip_unmute else R.string.sip_mute)) }
                OutlinedButton(onClick = { try { client.toggleSpeaker() } catch (_: Exception) { error = context.getString(R.string.sip_call_error) } }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(if (state.speaker) R.string.sip_earpiece else R.string.sip_speaker)) }
                Text(stringResource(if (state.srtpActive) R.string.sip_srtp_negotiated else R.string.sip_media_unverified), color = if (state.srtpActive) ReadyColor else WarningColor)
            }
        }
    }
    CallingRoute.entries.forEach { route ->
        val capability = if (route == CallingRoute.SIP_INTERNAL) {
            if (state.registration == SipRegistration.REGISTERED) RouteAvailability.NOT_VERIFIED
            else if (state.registration == SipRegistration.FAILED) RouteAvailability.OFFLINE else RouteAvailability.NEEDS_SETUP
        } else if (route == CallingRoute.CARRIER_WIFI && dashboard.phoneAsSim?.capability == PhoneAsSimCapability.CARRIER_PRIVILEGE_REQUIRED) {
            // Missing privileges concern this application's native engine, not the operator's own dialler.
            RouteAvailability.NOT_VERIFIED
        } else RouteAvailability.NOT_VERIFIED
        OutlinedCard(onClick = { if (!busy) selected = route }, modifier = Modifier.fillMaxWidth().testTag("route-${route.name.lowercase()}")) {
            Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Icon(when (route) { CallingRoute.CARRIER_WIFI -> Icons.Default.WifiCalling3; CallingRoute.EXTERNAL_USIM -> Icons.Default.SimCard; CallingRoute.CELLULAR_VOICE -> Icons.Default.Router; CallingRoute.SIP_INTERNAL -> Icons.Default.Call }, null, tint = MaterialTheme.colorScheme.primary)
                Column(Modifier.weight(1f)) {
                    Text(stringResource(routeTitle(route)), style = MaterialTheme.typography.titleSmall)
                    Text(stringResource(availabilityTitle(capability)), color = WarningColor)
                }
                RadioButton(selected == route, onClick = null)
            }
        }
    }
    if (selected != CallingRoute.SIP_INTERNAL) {
        Text(stringResource(when (selected) {
            CallingRoute.CARRIER_WIFI -> R.string.carrier_route_boundary
            CallingRoute.EXTERNAL_USIM -> R.string.usim_route_boundary
            else -> R.string.cellular_route_boundary
        }), color = WarningColor)
        return
    }
    Card(Modifier.fillMaxWidth().testTag("sip-setup")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(stringResource(R.string.sip_internal_boundary), color = WarningColor)
            OutlinedTextField(host, { host = it }, enabled = !busy, label = { Text(stringResource(R.string.sip_server)) }, singleLine = true, modifier = Modifier.fillMaxWidth().testTag("sip-server"))
            OutlinedTextField(port, { port = it.filter(Char::isDigit).take(5) }, enabled = !busy, label = { Text(stringResource(R.string.sip_tls_port)) }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(user, { user = it.filter(Char::isDigit).take(6) }, enabled = !busy, label = { Text(stringResource(R.string.sip_extension)) }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(password, { password = it }, enabled = !busy, label = { Text(stringResource(R.string.sip_password)) }, visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(stun, { stun = it }, enabled = !busy, label = { Text(stringResource(R.string.sip_stun_optional)) }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Text(stringResource(when (state.registration) { SipRegistration.REGISTERED -> R.string.sip_registered; SipRegistration.CONNECTING -> R.string.sip_connecting; SipRegistration.FAILED -> R.string.sip_failed; else -> R.string.sip_offline }), modifier = Modifier.testTag("sip-registration"))
            Button(enabled = !busy && state.registration != SipRegistration.CONNECTING && InternalDialPolicy.validHost(host.trim()) && InternalDialPolicy.validExtension(user) && password.length >= 8,
                onClick = {
                    val permissions = mutableListOf(Manifest.permission.RECORD_AUDIO)
                    if (Build.VERSION.SDK_INT >= 33) permissions += Manifest.permission.POST_NOTIFICATIONS
                    if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) register()
                    else permission.launch(permissions.toTypedArray())
                }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.sip_connect)) }
            if (state.registration != SipRegistration.OFFLINE) OutlinedButton(onClick = { client.disconnect() }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.sip_disconnect)) }
        }
    }
    Card(Modifier.fillMaxWidth().testTag("sip-dialler")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(stringResource(R.string.sip_dialler), style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(target, { target = it.filter(Char::isDigit).take(6) }, enabled = !busy, singleLine = true, label = { Text(stringResource(R.string.sip_destination)) }, modifier = Modifier.fillMaxWidth().testTag("sip-target"))
            OutlinedButton(enabled = !busy, onClick = {
                try { contacts.launch(Intent(Intent.ACTION_PICK, ContactsContract.CommonDataKinds.Phone.CONTENT_URI)) }
                catch (_: Exception) { error = context.getString(R.string.sip_contact_error) }
            }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Default.Contacts, null); Spacer(Modifier.width(8.dp)); Text(stringResource(R.string.sip_pick_contact)) }
            listOf("123", "456", "789", "0").forEach { row ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    row.forEach { digit -> OutlinedButton(onClick = { if (target.length < 6) target += digit }, enabled = !busy, modifier = Modifier.weight(1f).heightIn(min = 48.dp)) { Text(digit.toString()) } }
                    if (row == "0") OutlinedButton(onClick = { target = target.dropLast(1) }, enabled = !busy, modifier = Modifier.weight(1f).heightIn(min = 48.dp)) { Icon(Icons.Default.Backspace, stringResource(R.string.sip_delete_digit)) }
                }
            }
            Button(onClick = { try { client.dial(target); error = null } catch (_: Exception) { error = context.getString(R.string.sip_call_error) } },
                enabled = state.registration == SipRegistration.REGISTERED && !busy && InternalDialPolicy.validExtension(target), modifier = Modifier.fillMaxWidth().testTag("sip-call")) { Icon(Icons.Default.Call, null); Spacer(Modifier.width(8.dp)); Text(stringResource(R.string.sip_call)) }
            (error ?: state.error?.let { context.getString(R.string.sip_call_error) })?.let { Text(it, color = ErrorColor) }
        }
    }
    Text(stringResource(R.string.sip_history), style = MaterialTheme.typography.titleMedium)
    if (state.history.isEmpty()) Text(stringResource(R.string.sip_history_empty))
    else state.history.forEach { entry ->
        Text(stringResource(R.string.sip_history_entry, stringResource(if (entry.incoming) R.string.sip_incoming else R.string.sip_outgoing), entry.extension, entry.seconds))
    }
    Text(stringResource(R.string.sip_foreground_limit), color = WarningColor, style = MaterialTheme.typography.bodySmall)
}
private fun routeTitle(route: CallingRoute) = when (route) {
    CallingRoute.CARRIER_WIFI -> R.string.route_carrier
    CallingRoute.EXTERNAL_USIM -> R.string.route_usim
    CallingRoute.CELLULAR_VOICE -> R.string.route_cellular
    CallingRoute.SIP_INTERNAL -> R.string.route_sip
}
private fun availabilityTitle(status: RouteAvailability) = when (status) {
    RouteAvailability.AVAILABLE -> R.string.route_available
    RouteAvailability.NEEDS_SETUP -> R.string.route_needs_setup
    RouteAvailability.NOT_VERIFIED -> R.string.route_not_verified
    RouteAvailability.UNSUPPORTED_BY_EVIDENCE -> R.string.route_unsupported
    RouteAvailability.OFFLINE -> R.string.route_offline
}

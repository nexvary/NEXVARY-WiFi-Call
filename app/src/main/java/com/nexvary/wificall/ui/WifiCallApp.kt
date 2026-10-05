package com.nexvary.wificall.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.nexvary.wificall.BuildConfig
import com.nexvary.wificall.R
import com.nexvary.wificall.core.*
import com.nexvary.wificall.platform.PhoneAsSimCapability

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun WifiCallApp(
    initial: DashboardState = DemoState.value,
    onRequestPhonePermission: () -> Unit = {},
    onRefresh: () -> Unit = {},
    language: String = "",
    onLanguageChange: (String) -> Unit = {},
    onSelectSubscription: (Int) -> Unit = {},
    onModeChange: (AppMode) -> Unit = {}
) {
    var page by rememberSaveable { mutableStateOf(AppPage.HOME) }
    var returnPage by rememberSaveable { mutableStateOf(AppPage.HOME) }
    var mode by rememberSaveable { mutableStateOf(initial.mode) }
    LaunchedEffect(initial.mode) { mode = initial.mode }
    val tabs = listOf(AppPage.HOME, AppPage.SIMS, AppPage.DIAGNOSTICS, AppPage.SETTINGS)
    fun open(destination: AppPage) { returnPage = page; page = destination }
    fun back() { page = if (page in tabs) AppPage.HOME else returnPage }
    BackHandler(enabled = page != AppPage.HOME) { back() }
    Scaffold(
        topBar = { TopAppBar(
            title = { Text(stringResource(if (page == AppPage.HOME) R.string.app_name else page.title()), style = MaterialTheme.typography.titleLarge, maxLines = 1, overflow = TextOverflow.Ellipsis) },
            navigationIcon = { if (page != AppPage.HOME) IconButton(onClick = { back() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) } },
            actions = { IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, stringResource(R.string.refresh_check)) } },
            colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background)
        ) },
        bottomBar = { NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
            tabs.forEach { destination -> NavigationBarItem(
                modifier = Modifier.testTag("nav-${destination.name.lowercase()}"),
                selected = page == destination || (page !in tabs && returnPage == destination),
                onClick = { page = destination; returnPage = AppPage.HOME },
                icon = { Icon(destination.icon(), null, Modifier.size(24.dp)) },
                label = { Text(stringResource(if (destination == AppPage.SETTINGS) R.string.more else destination.title()), maxLines = 1, overflow = TextOverflow.Ellipsis) }
            ) }
        } }
    ) { padding -> key(page) { Page(Modifier.padding(padding)) {
        when (page) {
            AppPage.HOME -> {
                StatusRing(initial)
                Button(onClick = { onRefresh(); open(AppPage.DIAGNOSTICS) }, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) {
                    Icon(Icons.Default.Radar, null, Modifier.size(22.dp)); Spacer(Modifier.width(8.dp)); Text(stringResource(R.string.start_check))
                }
                if (initial.subscriptions.isNotEmpty()) initial.subscriptions.forEach { SimCard(it, initial, mode, false) { onSelectSubscription(it.id) } }
                else Action(R.string.sims, Icons.Default.SimCard) { open(AppPage.SIMS) }
                Action(R.string.changes, Icons.Default.History) { open(AppPage.CHANGES) }
                Action(R.string.compatibility, Icons.Default.VerifiedUser) { open(AppPage.COMPATIBILITY) }
            }
            AppPage.SIMS -> {
                InfoCard(stringResource(R.string.sim_summary))
                if (initial.phonePermissionRequired) {
                    InfoCard(stringResource(R.string.sim_permission))
                    Button(onClick = onRequestPhonePermission, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.allow_sim)) }
                } else if (initial.subscriptions.isEmpty()) InfoCard(stringResource(if (initial.telephonyUnavailable) R.string.capability_unavailable else R.string.no_sims))
                else initial.subscriptions.forEach { SimCard(it, initial, mode, true) { onSelectSubscription(it.id) } }
            }
            AppPage.CHANGES -> { if (initial.changes.isEmpty()) InfoCard(stringResource(R.string.no_changes)) else initial.changes.forEach { InfoCard(label(it)) } }
            AppPage.DIAGNOSTICS -> {
                ModeCard(mode) { mode = mode.toggle(); onModeChange(mode) }
                Pipeline(initial, mode)
                Metric(R.string.carrier_evidence, label(initial.evidence))
                if (mode == AppMode.LAB) { Metric(R.string.path, label(initial.readiness.path)); Metric(R.string.entitlement, label(initial.entitlement)); Metric(R.string.network_quality, label(initial.quality.grade)) }
            }
            AppPage.COMPATIBILITY -> { Metric(R.string.carrier_evidence, label(initial.evidence)); InfoCard(stringResource(R.string.compatibility_explanation)) }
            AppPage.PRIVACY -> { InfoCard(stringResource(R.string.privacy_simple)); InfoCard(stringResource(R.string.privacy_secrets)); InfoCard(stringResource(R.string.privacy_exports)) }
            AppPage.ABOUT -> AboutDeveloperScreen()
            AppPage.SETTINGS -> {
                ModeCard(mode) { mode = mode.toggle(); onModeChange(mode) }
                LanguagePicker(language, onLanguageChange)
                Action(R.string.privacy, Icons.Default.PrivacyTip) { open(AppPage.PRIVACY) }
                Action(R.string.about_developer, Icons.Default.Business) { open(AppPage.ABOUT) }
                Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(R.string.about_app), style = MaterialTheme.typography.titleMedium)
                    Text(stringResource(R.string.app_name), color = MaterialTheme.colorScheme.primary)
                    Text(stringResource(R.string.version) + " · " + BuildConfig.VERSION_NAME + " (" + BuildConfig.VERSION_CODE + ")", style = MaterialTheme.typography.bodyMedium.copy(textDirection = TextDirection.Ltr))
                    Text(stringResource(R.string.gateway_not_configured), color = MaterialTheme.colorScheme.onSurfaceVariant)
                } }
            }
        }
    } } }
}
private fun AppMode.toggle() = if (this == AppMode.CONSUMER) AppMode.LAB else AppMode.CONSUMER
private fun AppPage.title() = when (this) {
    AppPage.HOME -> R.string.home; AppPage.SIMS -> R.string.sims; AppPage.CHANGES -> R.string.changes
    AppPage.DIAGNOSTICS -> R.string.diagnostics; AppPage.COMPATIBILITY -> R.string.compatibility
    AppPage.PRIVACY -> R.string.privacy; AppPage.ABOUT -> R.string.about_developer; AppPage.SETTINGS -> R.string.settings
}
private fun AppPage.icon(): ImageVector = when (this) { AppPage.HOME -> Icons.Default.Home; AppPage.SIMS -> Icons.Default.SimCard; AppPage.DIAGNOSTICS -> Icons.Default.Troubleshoot; else -> Icons.Default.Settings }
@Composable private fun Page(modifier: Modifier, body: @Composable ColumnScope.() -> Unit) {
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = body)
}
@Composable private fun StatusRing(state: DashboardState) {
    val ready = state.readiness.state in setOf(ReadinessState.READY_NATIVE, ReadinessState.READY_GATEWAY, ReadinessState.READY_SIP)
    val unavailable = state.readiness.state == ReadinessState.UNSUPPORTED || state.telephonyUnavailable
    val action = state.phonePermissionRequired || Blocker.SIM_NOT_SELECTED in state.readiness.blockers || state.readiness.state in setOf(ReadinessState.DEGRADED, ReadinessState.RESTRICTED)
    val color = when { state.checking -> MaterialTheme.colorScheme.primary; ready -> ReadyColor; unavailable -> ErrorColor; action -> WarningColor; else -> UnknownColor }
    val title = when { state.checking -> R.string.status_checking; ready -> R.string.status_ready; unavailable -> R.string.status_unavailable; action -> R.string.status_action; else -> R.string.status_not_checked }
    val track = MaterialTheme.colorScheme.surfaceVariant
    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(stringResource(R.string.ready_title), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Box(Modifier.size(160.dp).testTag("status-ring"), contentAlignment = Alignment.Center) {
            Canvas(Modifier.fillMaxSize().padding(6.dp)) {
                drawCircle(track, style = Stroke(10.dp.toPx()))
                drawArc(color, -90f, if (ready) 360f else 280f, false, style = Stroke(10.dp.toPx(), cap = StrokeCap.Round))
            }
            Icon(if (ready) Icons.Default.WifiCalling3 else Icons.Default.WifiCalling, null, Modifier.size(60.dp), tint = color)
        }
        Text(stringResource(title), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = color)
        Text(if (state.checking) stringResource(R.string.check_in_progress) else if (state.phonePermissionRequired) stringResource(R.string.capability_permission) else state.readiness.blockers.firstOrNull()?.let { label(it) } ?: stringResource(R.string.check_summary), style = MaterialTheme.typography.bodyMedium)
    } }
}
@Composable private fun SimCard(sim: SubscriptionRef, state: DashboardState, mode: AppMode, expanded: Boolean, select: () -> Unit) {
    val selected = sim.id == state.selectedSubscriptionId
    OutlinedCard(onClick = select, modifier = Modifier.fillMaxWidth().testTag("sim-${sim.id}"), border = BorderStroke(1.dp, if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Icon(Icons.Default.SimCard, null, Modifier.size(28.dp), tint = MaterialTheme.colorScheme.primary)
                Column(Modifier.weight(1f)) { Text(stringResource(R.string.sim_slot, sim.slotIndex + 1), style = MaterialTheme.typography.labelLarge); Text(sim.carrierName ?: stringResource(R.string.unknown_carrier), style = MaterialTheme.typography.titleMedium) }
                RadioButton(selected, onClick = null)
            }
            Text(stringResource(if (selected) R.string.selected else R.string.not_selected), color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)
            if (expanded) {
                Text(stringResource(R.string.detected), color = ReadyColor, style = MaterialTheme.typography.bodyMedium)
                Text(stringResource(R.string.vo_wifi) + " · " + stringResource(R.string.not_tested), style = MaterialTheme.typography.bodyMedium)
                Text(stringResource(R.string.phone_as_sim) + " · " + capabilityLabel(state.phoneAsSimBySubscription[sim.id]?.capability), style = MaterialTheme.typography.bodyMedium)
                Text(stringResource(R.string.aka_not_tested), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                if (mode == AppMode.LAB) Text("MCC: ${sim.mcc ?: "—"} / MNC: ${sim.mnc ?: "—"}", style = MaterialTheme.typography.bodySmall.copy(textDirection = TextDirection.Ltr))
            }
        }
    }
}
@Composable private fun capabilityLabel(capability: PhoneAsSimCapability?): String = stringResource(when (capability) {
    PhoneAsSimCapability.AVAILABLE_BY_CARRIER_PRIVILEGE -> R.string.capability_available
    PhoneAsSimCapability.CARRIER_PRIVILEGE_REQUIRED -> R.string.capability_privilege
    PhoneAsSimCapability.PERMISSION_REQUIRED -> R.string.capability_permission
    PhoneAsSimCapability.NO_ACTIVE_SUBSCRIPTION, PhoneAsSimCapability.SIM_NOT_SELECTED -> R.string.capability_no_sim
    PhoneAsSimCapability.TELEPHONY_UNAVAILABLE -> R.string.capability_unavailable
    PhoneAsSimCapability.UNSUPPORTED -> R.string.capability_unsupported
    null -> R.string.not_tested
})
@Composable private fun Pipeline(state: DashboardState, mode: AppMode) {
    Stage(R.string.sims, Icons.Default.SimCard, if (state.phonePermissionRequired) stringResource(R.string.capability_permission) else if (state.selectedSubscriptionId != null) stringResource(R.string.detected) else stringResource(R.string.capability_no_sim), if (state.selectedSubscriptionId != null) ReadyColor else WarningColor, mode, "SIM", "diagnostics-sim")
    val connected = state.network.wifi && state.network.internetValidated && !state.network.captivePortal
    Stage(R.string.network, Icons.Default.Wifi, stringResource(if (connected) R.string.network_connected else R.string.network_unavailable), if (connected) ReadyColor else WarningColor, mode, "Wi-Fi=${state.network.wifi}; validated=${state.network.internetValidated}; captive=${state.network.captivePortal}; VPN=${state.network.vpn}", "diagnostics-network")
    val capability = state.phoneAsSim?.capability
    Stage(R.string.phone_as_sim, Icons.Default.Security, capabilityLabel(capability), if (capability == PhoneAsSimCapability.AVAILABLE_BY_CARRIER_PRIVILEGE) ReadyColor else WarningColor, mode, state.phoneAsSim?.detail ?: stringResource(R.string.not_tested), "diagnostics-phone-as-sim", stringResource(R.string.aka_not_tested))
    listOf(Triple(R.string.epdg, Icons.Default.Cloud, "ePDG"), Triple(R.string.ipsec, Icons.Default.VpnLock, "IKEv2 / IPsec"), Triple(R.string.ims, Icons.Default.Hub, "IMS REGISTER / P-CSCF"), Triple(R.string.calling, Icons.Default.Call, "SIP outbound / inbound"), Triple(R.string.audio, Icons.Default.GraphicEq, "RTP bidirectional audio")).forEach { (title, icon, evidence) ->
        Stage(title, icon, stringResource(R.string.not_tested), UnknownColor, mode, evidence + ": " + stringResource(R.string.not_tested), if (title == R.string.audio) "diagnostics-audio" else "diagnostics-$title", stringResource(R.string.pipeline_unverified))
    }
}
@Composable private fun Stage(title: Int, icon: ImageVector, status: String, color: Color, mode: AppMode, evidence: String, tag: String, explanation: String? = null) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    OutlinedCard(onClick = { expanded = !expanded }, modifier = Modifier.fillMaxWidth().testTag(tag), border = BorderStroke(1.dp, color.copy(alpha = 0.4f))) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Icon(icon, null, Modifier.size(26.dp), tint = color)
                Column(Modifier.weight(1f)) { Text(stringResource(title), style = MaterialTheme.typography.titleMedium); Text(status, style = MaterialTheme.typography.bodyMedium, color = color) }
                Icon(if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore, stringResource(R.string.details), Modifier.size(20.dp))
            }
            if (expanded) { explanation?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }; if (mode == AppMode.LAB) { Text(stringResource(R.string.technical_evidence), style = MaterialTheme.typography.labelMedium); Text(evidence, style = MaterialTheme.typography.bodySmall.copy(textDirection = TextDirection.Ltr)) } }
        }
    }
}
@Composable private fun ModeCard(mode: AppMode, change: () -> Unit) {
    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Icon(if (mode == AppMode.LAB) Icons.Default.Science else Icons.Default.Person, null, tint = MaterialTheme.colorScheme.primary)
            Column(Modifier.weight(1f)) { Text(stringResource(R.string.mode), style = MaterialTheme.typography.labelMedium); Text(stringResource(if (mode == AppMode.LAB) R.string.lab_mode else R.string.consumer_mode), style = MaterialTheme.typography.titleMedium) }
            Switch(checked = mode == AppMode.LAB, onCheckedChange = { change() }, modifier = Modifier.testTag("lab-mode-switch"))
        }
        Text(stringResource(if (mode == AppMode.LAB) R.string.lab_explanation else R.string.consumer_explanation), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    } }
}
@Composable private fun Metric(title: Int, value: String) { Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) { Text(stringResource(title), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant); Text(value, style = MaterialTheme.typography.titleMedium) } } }
@Composable private fun InfoCard(text: String) { Card(Modifier.fillMaxWidth()) { Text(text, Modifier.padding(16.dp), style = MaterialTheme.typography.bodyLarge) } }
@Composable private fun Action(title: Int, icon: ImageVector, click: () -> Unit) { OutlinedCard(onClick = click, modifier = Modifier.fillMaxWidth()) { Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) { Icon(icon, null, Modifier.size(24.dp), tint = MaterialTheme.colorScheme.primary); Text(stringResource(title), style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f)); Icon(Icons.Default.ChevronRight, null, Modifier.size(20.dp)) } } }
@Composable private fun LanguagePicker(language: String, change: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val languages = linkedMapOf("" to stringResource(R.string.follow_system), "ar" to "العربية", "en" to "English", "tr" to "Türkçe", "es" to "Español", "de" to "Deutsch", "it" to "Italiano", "fr" to "Français")
    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp)) { Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) { Icon(Icons.Default.Language, null, tint = MaterialTheme.colorScheme.primary); Text(stringResource(R.string.language), style = MaterialTheme.typography.titleMedium) }; Box { TextButton(onClick = { expanded = true }) { Text(languages[language] ?: languages.getValue("")) }; DropdownMenu(expanded, onDismissRequest = { expanded = false }) { languages.forEach { (code, name) -> DropdownMenuItem(text = { Text(name) }, onClick = { expanded = false; change(code) }) } } } } }
}

@Composable private fun label(value: Enum<*>): String = stringResource(when (value) {
    ReadinessState.READY_NATIVE -> R.string.ready_native
    ReadinessState.READY_GATEWAY -> R.string.ready_gateway
    ReadinessState.READY_SIP -> R.string.ready_sip
    ReadinessState.DEGRADED -> R.string.degraded
    ReadinessState.RESTRICTED -> R.string.restricted
    ReadinessState.UNSUPPORTED -> R.string.unsupported
    ReadinessState.UNKNOWN -> R.string.unknown
    CallPath.NATIVE_CARRIER -> R.string.native_path
    CallPath.EXTERNAL_GATEWAY -> R.string.gateway_path
    CallPath.SIP_FALLBACK -> R.string.sip_path
    CallPath.UNAVAILABLE -> R.string.no_path
    QualityGrade.EXCELLENT -> R.string.quality_excellent
    QualityGrade.GOOD -> R.string.quality_good
    QualityGrade.FAIR -> R.string.quality_fair
    QualityGrade.POOR -> R.string.quality_poor
    QualityGrade.UNKNOWN -> R.string.quality_unknown
    EvidenceLevel.UNKNOWN -> R.string.evidence_unknown
    EvidenceLevel.DISCOVERED -> R.string.evidence_discovered
    EvidenceLevel.EPDG_REACHABLE -> R.string.evidence_epdg_reachable
    EvidenceLevel.SWU_AUTHENTICATED -> R.string.evidence_swu_authenticated
    EvidenceLevel.IMS_REGISTERED -> R.string.evidence_ims_registered
    EvidenceLevel.OUTBOUND_VOICE_VERIFIED -> R.string.evidence_outbound_voice_verified
    EvidenceLevel.INBOUND_VOICE_VERIFIED -> R.string.evidence_inbound_voice_verified
    EvidenceLevel.PRODUCTION_CANDIDATE -> R.string.evidence_production_candidate
    EntitlementState.UNKNOWN -> R.string.entitlement_unknown
    EntitlementState.NOT_APPLICABLE -> R.string.entitlement_not_applicable
    EntitlementState.ELIGIBLE -> R.string.entitlement_eligible
    EntitlementState.ACTIVATION_REQUIRED -> R.string.entitlement_activation_required
    EntitlementState.ENABLED -> R.string.entitlement_enabled
    EntitlementState.DISABLED -> R.string.entitlement_disabled
    EntitlementState.RESTRICTED -> R.string.entitlement_restricted
    Blocker.NO_WIFI -> R.string.blocker_no_wifi
    Blocker.CAPTIVE_PORTAL -> R.string.blocker_captive_portal
    Blocker.INTERNET_NOT_VALIDATED -> R.string.blocker_internet_not_validated
    Blocker.SIM_NOT_SELECTED -> R.string.blocker_sim_not_selected
    Blocker.PLATFORM_RESTRICTED -> R.string.blocker_platform_restricted
    Blocker.CARRIER_EVIDENCE_MISSING -> R.string.blocker_carrier_evidence_missing
    Blocker.PATH_UNHEALTHY -> R.string.blocker_path_unhealthy
    ChangeReason.WIFI_LOST -> R.string.change_wifi_lost
    ChangeReason.WIFI_GAINED -> R.string.change_wifi_gained
    ChangeReason.VALIDATION_LOST -> R.string.change_validation_lost
    ChangeReason.VALIDATION_GAINED -> R.string.change_validation_gained
    ChangeReason.CAPTIVE_PORTAL_APPEARED -> R.string.change_captive_portal_appeared
    ChangeReason.CAPTIVE_PORTAL_CLEARED -> R.string.change_captive_portal_cleared
    ChangeReason.VPN_ENABLED -> R.string.change_vpn_enabled
    ChangeReason.VPN_DISABLED -> R.string.change_vpn_disabled
    ChangeReason.DNS_CHANGED -> R.string.change_dns_changed
    ChangeReason.QUALITY_DEGRADED -> R.string.change_quality_degraded
    ChangeReason.QUALITY_IMPROVED -> R.string.change_quality_improved
    else -> R.string.unknown
})

package com.nexvary.wificall.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.nexvary.wificall.R
import com.nexvary.wificall.core.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WifiCallApp(
    initial: DashboardState = DemoState.value,
    onRequestPhonePermission: () -> Unit = {},
    onRefresh: () -> Unit = {},
    language: String = "",
    onLanguageChange: (String) -> Unit = {},
    onSelectSubscription: (Int) -> Unit = {}
) {
    var page by rememberSaveable { mutableStateOf(AppPage.HOME) }
    var returnPage by rememberSaveable { mutableStateOf(AppPage.HOME) }
    var mode by rememberSaveable { mutableStateOf(initial.mode) }
    val tabs = listOf(AppPage.HOME, AppPage.SIMS, AppPage.DIAGNOSTICS, AppPage.SETTINGS)
    fun open(destination: AppPage) { returnPage = page; page = destination }
    fun back() { page = if (page in tabs) AppPage.HOME else returnPage }
    BackHandler(enabled = page != AppPage.HOME) { back() }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(if (page == AppPage.HOME) R.string.app_name else page.title()), style = MaterialTheme.typography.titleLarge) },
                navigationIcon = {
                    if (page != AppPage.HOME) IconButton(onClick = { back() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back))
                    }
                },
                actions = { IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, stringResource(R.string.refresh_check)) } }
            )
        },
        bottomBar = {
            NavigationBar {
                tabs.forEach { destination ->
                    NavigationBarItem(
                        selected = page == destination || (page !in tabs && returnPage == destination),
                        onClick = { page = destination; returnPage = AppPage.HOME },
                        icon = { Icon(destination.icon(), null) },
                        label = { Text(stringResource(if (destination == AppPage.SETTINGS) R.string.more else destination.title())) }
                    )
                }
            }
        }
    ) { padding ->
        Page(Modifier.padding(padding)) {
            when (page) {
                AppPage.HOME -> {
                    ReadinessCard(initial)
                    Button(onClick = { onRefresh(); open(AppPage.DIAGNOSTICS) }, modifier = Modifier.fillMaxWidth()) {
                        Icon(Icons.Default.CheckCircle, null, Modifier.size(20.dp)); Spacer(Modifier.width(8.dp))
                        Text(stringResource(R.string.start_check))
                    }
                    Metric(R.string.network_quality, label(initial.quality.grade))
                    Action(R.string.changes, Icons.Default.Refresh) { open(AppPage.CHANGES) }
                    Action(R.string.compatibility, Icons.Default.Info) { open(AppPage.COMPATIBILITY) }
                }
                AppPage.SIMS -> {
                    if (initial.phonePermissionRequired) {
                        InfoCard(stringResource(R.string.sim_permission))
                        Button(onClick = onRequestPhonePermission, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.allow_sim)) }
                    } else if (initial.subscriptions.isEmpty()) InfoCard(stringResource(R.string.no_sims))
                    else initial.subscriptions.forEach { sim ->
                        OutlinedCard(onClick = { onSelectSubscription(sim.id) }, modifier = Modifier.fillMaxWidth()) {
                            Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                RadioButton(selected = sim.id == initial.selectedSubscriptionId, onClick = null)
                                Column(Modifier.weight(1f)) {
                                    Text(stringResource(R.string.sim_slot, sim.slotIndex + 1), style = MaterialTheme.typography.labelLarge)
                                    Text(sim.carrierName ?: stringResource(R.string.unknown_carrier), style = MaterialTheme.typography.titleMedium)
                                }
                            }
                        }
                    }
                }
                AppPage.CHANGES -> {
                    if (initial.changes.isEmpty()) InfoCard(stringResource(R.string.no_changes))
                    else initial.changes.forEach { InfoCard(label(it)) }
                }
                AppPage.DIAGNOSTICS -> {
                    ReadinessCard(initial)
                    Metric(R.string.path, label(initial.readiness.path))
                    Metric(R.string.network_quality, label(initial.quality.grade))
                    Metric(R.string.carrier_evidence, label(initial.evidence))
                    Metric(R.string.entitlement, label(initial.entitlement))
                    Metric(R.string.mode, stringResource(if (mode == AppMode.CONSUMER) R.string.consumer_mode else R.string.lab_mode))
                    initial.readiness.blockers.forEach { InfoCard(label(it)) }
                    if (mode == AppMode.LAB) InfoCard(stringResource(R.string.lab_explanation))
                    OutlinedButton(onClick = { mode = mode.toggle() }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.switch_mode)) }
                }
                AppPage.COMPATIBILITY -> {
                    Metric(R.string.carrier_evidence, label(initial.evidence))
                    InfoCard(stringResource(R.string.compatibility_explanation))
                }
                AppPage.PRIVACY -> {
                    InfoCard(stringResource(R.string.privacy_secrets))
                    InfoCard(stringResource(R.string.privacy_exports))
                }
                AppPage.ABOUT -> AboutDeveloperScreen()
                AppPage.SETTINGS -> {
                    Metric(R.string.mode, stringResource(if (mode == AppMode.CONSUMER) R.string.consumer_mode else R.string.lab_mode))
                    OutlinedButton(onClick = { mode = mode.toggle() }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.switch_mode)) }
                    LanguagePicker(language, onLanguageChange)
                    Action(R.string.privacy, Icons.Default.Info) { open(AppPage.PRIVACY) }
                    Action(R.string.about_developer, Icons.Default.Info) { open(AppPage.ABOUT) }
                }
            }
        }
    }
}

private fun AppMode.toggle() = if (this == AppMode.CONSUMER) AppMode.LAB else AppMode.CONSUMER
private fun AppPage.title() = when (this) {
    AppPage.HOME -> R.string.home; AppPage.SIMS -> R.string.sims
    AppPage.CHANGES -> R.string.changes; AppPage.DIAGNOSTICS -> R.string.diagnostics
    AppPage.COMPATIBILITY -> R.string.compatibility; AppPage.PRIVACY -> R.string.privacy
    AppPage.ABOUT -> R.string.about_developer; AppPage.SETTINGS -> R.string.settings
}
private fun AppPage.icon(): ImageVector = when (this) {
    AppPage.HOME -> Icons.Default.Home; AppPage.SIMS -> Icons.Default.Phone
    AppPage.DIAGNOSTICS -> Icons.Default.CheckCircle; else -> Icons.Default.Settings
}

@Composable private fun Page(modifier: Modifier, body: @Composable ColumnScope.() -> Unit) {
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = body)
}
@Composable private fun ReadinessCard(state: DashboardState) {
    val ready = state.readiness.state in setOf(ReadinessState.READY_NATIVE, ReadinessState.READY_GATEWAY, ReadinessState.READY_SIP)
    OutlinedCard(Modifier.fillMaxWidth(), border = BorderStroke(1.dp, if (ready) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline)) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.ready_title), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            Text(label(state.readiness.state), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(stringResource(R.string.check_summary), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
@Composable private fun Metric(title: Int, value: String) {
    OutlinedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(stringResource(title), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, style = MaterialTheme.typography.titleMedium)
        }
    }
}
@Composable private fun InfoCard(text: String) {
    Card(Modifier.fillMaxWidth()) { Text(text, Modifier.padding(16.dp), style = MaterialTheme.typography.bodyLarge) }
}
@Composable private fun Action(title: Int, icon: ImageVector, click: () -> Unit) {
    OutlinedCard(onClick = click, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Icon(icon, null, Modifier.size(24.dp), tint = MaterialTheme.colorScheme.primary)
            Text(stringResource(title), style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
        }
    }
}
@Composable private fun LanguagePicker(language: String, change: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val languages = linkedMapOf("" to stringResource(R.string.follow_system), "ar" to "العربية", "en" to "English", "tr" to "Türkçe", "es" to "Español", "de" to "Deutsch", "it" to "Italiano", "fr" to "Français")
    OutlinedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text(stringResource(R.string.language), style = MaterialTheme.typography.labelLarge)
            Box {
                TextButton(onClick = { expanded = true }) { Text(languages[language] ?: languages.getValue("")) }
                DropdownMenu(expanded, onDismissRequest = { expanded = false }) {
                    languages.forEach { (code, name) -> DropdownMenuItem(text = { Text(name) }, onClick = { expanded = false; change(code) }) }
                }
            }
        }
    }
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

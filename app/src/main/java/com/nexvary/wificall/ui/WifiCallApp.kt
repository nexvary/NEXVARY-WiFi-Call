package com.nexvary.wificall.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.nexvary.wificall.core.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun WifiCallApp(initial:DashboardState=DemoState.value){ var page by remember{mutableStateOf(AppPage.HOME)}; var mode by remember{mutableStateOf(initial.mode)}; Scaffold(topBar={TopAppBar(title={Text("NEXVARY WiFi Call")})},bottomBar={NavigationBar{listOf(AppPage.HOME to "Home",AppPage.SIMS to "SIMs",AppPage.DIAGNOSTICS to "Check",AppPage.SETTINGS to "More").forEach{(p,l)->NavigationBarItem(selected=page==p,onClick={page=p},icon={},label={Text(l)})}}}){pad->Box(Modifier.padding(pad).fillMaxSize()){when(page){AppPage.HOME->Home(initial.copy(mode=mode)){page=it};AppPage.SIMS->Sims(initial);AppPage.CHANGES->Changes(initial);AppPage.DIAGNOSTICS->Diagnostics(initial,mode){mode=it};AppPage.COMPATIBILITY->Compatibility(initial);AppPage.PRIVACY->Privacy();AppPage.ABOUT->AboutDeveloperScreen();AppPage.SETTINGS->Settings(mode,{mode=it}){page=it}}}} }
@Composable private fun Home(s:DashboardState,open:(AppPage)->Unit)=Page("Calling readiness"){Metric("State",s.readiness.state.name);Metric("Path",s.readiness.path.name);Metric("Network quality",s.quality.grade.name);Metric("Carrier evidence",s.evidence.name);Metric("VoWiFi entitlement",s.entitlement.name);Button({open(AppPage.DIAGNOSTICS)},Modifier.fillMaxWidth()){Text("Run readiness check")};OutlinedButton({open(AppPage.CHANGES)},Modifier.fillMaxWidth()){Text("What changed?")};OutlinedButton({open(AppPage.COMPATIBILITY)},Modifier.fillMaxWidth()){Text("Compatibility evidence")}}
@Composable private fun Sims(s:DashboardState)=Page("SIM comparison"){if(s.subscriptions.isEmpty())Text("Permission or active subscription data is required.") else s.subscriptions.forEach{Metric("SIM "+(it.slotIndex+1),(it.carrierName?:"Unknown carrier"))}}
@Composable private fun Changes(s:DashboardState)=Page("What changed?"){if(s.changes.isEmpty())Text("No recorded network transition yet.") else s.changes.forEach{Text("• "+it.name)}}
@Composable private fun Diagnostics(s:DashboardState,m:AppMode,set:(AppMode)->Unit)=Page("Diagnostics"){Metric("Mode",m.name);Metric("State",s.readiness.state.name);s.readiness.blockers.forEach{Text("• "+it.name)};if(m==AppMode.LAB)Text("Lab mode exposes evidence and transport diagnostics, never SIM secrets.");Button({set(if(m==AppMode.CONSUMER)AppMode.LAB else AppMode.CONSUMER)}){Text("Switch mode")}}
@Composable private fun Compatibility(s:DashboardState)=Page("Compatibility"){Metric("Evidence",s.evidence.name);Text("Discovery alone is never presented as verified calling.")}
@Composable private fun Privacy()=Page("Privacy"){Text("SIM long-term authentication secrets are never extracted or stored.");Text("Diagnostic exports are redacted before sharing.")}
@Composable private fun Settings(m:AppMode,set:(AppMode)->Unit,open:(AppPage)->Unit)=Page("Settings"){Metric("Mode",m.name);Button({set(if(m==AppMode.CONSUMER)AppMode.LAB else AppMode.CONSUMER)}){Text("Toggle Consumer / Lab")};OutlinedButton({open(AppPage.PRIVACY)}){Text("Privacy & diagnostic export")};OutlinedButton({open(AppPage.ABOUT)}){Text("عن المطور")}}
@Composable private fun Metric(a:String,b:String){ElevatedCard(Modifier.fillMaxWidth()){Row(Modifier.padding(14.dp).fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(a);Text(b)}}}
@Composable private fun Page(title:String,body:@Composable ColumnScope.()->Unit){Column(Modifier.padding(20.dp).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp)){Text(title,style=MaterialTheme.typography.headlineSmall);body()}}

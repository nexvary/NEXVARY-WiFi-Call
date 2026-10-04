package com.nexvary.wificall

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { CapabilityLab() } }
    }
}

@Composable
private fun CapabilityLab() {
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("NEXVARY WiFi Call", style = MaterialTheme.typography.headlineMedium)
            Text("Capability Lab", style = MaterialTheme.typography.titleLarge)
            Text("Foundation build for standards-oriented Wi-Fi Calling research.")
            Text("Carrier support is shown only after real interoperability verification.")
        }
    }
}

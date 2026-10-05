package com.nexvary.wificall.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val NexvaryColors = darkColorScheme(
    primary = Color(0xFF65D9D0), onPrimary = Color(0xFF003733),
    secondary = Color(0xFFBAC7D9), background = Color(0xFF071018),
    surface = Color(0xFF0E1B28), surfaceVariant = Color(0xFF1C2B3A),
    onBackground = Color(0xFFEAF1F8), onSurface = Color(0xFFEAF1F8),
    onSurfaceVariant = Color(0xFFBAC7D9), outline = Color(0xFF6E8298)
)

@Composable fun NexvaryTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = NexvaryColors, content = content)
}

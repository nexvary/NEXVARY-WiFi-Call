package com.nexvary.wificall.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

internal val ReadyColor = Color(0xFF22C55E)
internal val WarningColor = Color(0xFFF59E0B)
internal val ErrorColor = Color(0xFFEF4444)
internal val UnknownColor = Color(0xFF9FB0BE)
private val NexvaryColors = darkColorScheme(
    primary = Color(0xFF00D4FF), onPrimary = Color(0xFF071018),
    primaryContainer = Color(0xFF12374A), onPrimaryContainer = Color(0xFF00D4FF),
    secondary = Color(0xFF2979FF), secondaryContainer = Color(0xFF12374A),
    onSecondaryContainer = Color(0xFF00D4FF), background = Color(0xFF071018),
    surface = Color(0xFF101C27), surfaceVariant = Color(0xFF172B3B),
    surfaceContainer = Color(0xFF101C27), surfaceContainerLow = Color(0xFF101C27),
    surfaceContainerHigh = Color(0xFF101C27), surfaceContainerHighest = Color(0xFF101C27),
    surfaceContainerLowest = Color(0xFF071018), surfaceTint = Color(0xFF00D4FF),
    onBackground = Color(0xFFF3F7FA), onSurface = Color(0xFFF3F7FA),
    onSurfaceVariant = Color(0xFF9FB0BE), outline = Color(0xFF39566D),
    error = ErrorColor
)
@Composable fun NexvaryTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = NexvaryColors, content = content)
}

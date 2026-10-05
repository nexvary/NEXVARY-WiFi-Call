package com.nexvary.wificall.ui

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.ui.unit.dp
import com.nexvary.wificall.BuildConfig
import com.nexvary.wificall.R

@Composable fun AboutDeveloperScreen() {
    val context = LocalContext.current
    val linkError = stringResource(R.string.open_link_failed)
    fun open(url: String, action: String = Intent.ACTION_VIEW) {
        try { context.startActivity(Intent(action, Uri.parse(url))) }
        catch (_: ActivityNotFoundException) { Toast.makeText(context, linkError, Toast.LENGTH_LONG).show() }
        catch (_: SecurityException) { Toast.makeText(context, linkError, Toast.LENGTH_LONG).show() }
    }
    OutlinedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.about_bismillah), style = MaterialTheme.typography.bodyMedium)
            Text("FG MACHINES", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(stringResource(R.string.about_business), color = MaterialTheme.colorScheme.primary)
            Text(stringResource(R.string.about_description))
            Text(BuildConfig.VERSION_NAME, style = MaterialTheme.typography.labelLarge.copy(textDirection = TextDirection.Ltr))
        }
    }
    Button(onClick = { open("https://fgmachines.org") }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Default.Language, null, Modifier.size(20.dp)); Spacer(Modifier.width(8.dp)); Text(stringResource(R.string.official_website)) }
    OutlinedButton(onClick = { open("mailto:info@fgmachines.org", Intent.ACTION_SENDTO) }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Default.Email, null, Modifier.size(20.dp)); Spacer(Modifier.width(8.dp)); Text(stringResource(R.string.email)) }
    OutlinedButton(onClick = { open("https://www.facebook.com/share/1EKVAyZZ2C/") }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Default.Facebook, null, Modifier.size(20.dp)); Spacer(Modifier.width(8.dp)); Text(stringResource(R.string.personal_page)) }
    OutlinedButton(onClick = { open("https://www.facebook.com/share/1T7r3WpH8Y/") }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Default.Facebook, null, Modifier.size(20.dp)); Spacer(Modifier.width(8.dp)); Text(stringResource(R.string.business_page)) }
}

package com.nexvary.wificall.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

private const val FG_FACEBOOK="https://www.facebook.com/share/1T7r3WpH8Y/"
private const val ALAA_FACEBOOK="https://www.facebook.com/share/1EKVAyZZ2C/"
private const val FG_WEBSITE="https://fgmachines.org"
private const val FG_EMAIL="info@fgmachines.org"

@Composable fun AboutDeveloperScreen(){
 val context=LocalContext.current
 fun open(url:String){context.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(url)))}
 Column(Modifier.fillMaxSize().padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){
  Text("عن المطور",style=MaterialTheme.typography.headlineSmall,fontWeight=FontWeight.Bold)
  ElevatedCard(Modifier.fillMaxWidth()){Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
   Text("FG MACHINES",style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold)
   Text("للتجارة والتسويق")
   Text("بسم الله الرحمن الرحيم")
   Text("تم تطوير البرنامج بواسطة FG Machines. المطور الرئيسي: علاء محمد. وهذا البرنامج مجاني بالكامل لوجه الله.")
  }}
  Button({open(FG_WEBSITE)},Modifier.fillMaxWidth()){Text("الموقع الرسمي · fgmachines.org")}
  OutlinedButton({context.startActivity(Intent(Intent.ACTION_SENDTO,Uri.parse("mailto:"+FG_EMAIL)))},Modifier.fillMaxWidth()){Text("البريد الإلكتروني · info@fgmachines.org")}
  Text("روابط المطور",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)
  Text("الحساب الشخصي والصفحة التجارية")
  OutlinedButton({open(ALAA_FACEBOOK)},Modifier.fillMaxWidth()){Text("رابط الحساب الشخصي")}
  OutlinedButton({open(FG_FACEBOOK)},Modifier.fillMaxWidth()){Text("رابط الصفحة التجارية")}
 }
}

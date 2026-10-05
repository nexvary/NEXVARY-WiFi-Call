package com.nexvary.wificall

import android.Manifest
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import com.nexvary.wificall.ui.DashboardLoader
import com.nexvary.wificall.ui.WifiCallApp

class MainActivity:ComponentActivity(){
 override fun onCreate(savedInstanceState:Bundle?){
  super.onCreate(savedInstanceState)
  setContent{
   MaterialTheme{
    val context=LocalContext.current
    var refresh by remember{mutableIntStateOf(0)}
    val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()){refresh++}
    val state=remember(refresh){DashboardLoader.load(context)}
    WifiCallApp(initial=state,onRequestPhonePermission={permission.launch(Manifest.permission.READ_PHONE_STATE)})
   }
  }
 }
}

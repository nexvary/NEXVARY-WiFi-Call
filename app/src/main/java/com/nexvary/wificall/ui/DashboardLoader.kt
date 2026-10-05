package com.nexvary.wificall.ui

import android.content.Context
import com.nexvary.wificall.core.*
import com.nexvary.wificall.platform.AndroidNetworkProbe
import com.nexvary.wificall.platform.AndroidSubscriptionProbe

object DashboardLoader {
 fun load(context:Context):DashboardState {
  val network=AndroidNetworkProbe(context).snapshot()
  val subsResult=AndroidSubscriptionProbe(context).active()
  val subs=when(subsResult){is SubscriptionResult.Available->subsResult.subscriptions;else->emptyList()}
  val permissionRestricted=subsResult is SubscriptionResult.PermissionRequired
  val input=ReadinessInput(network=network,simSelected=subs.size==1,platformRestricted=permissionRestricted,nativeVerified=false,gatewayHealthy=false,sipReady=false,carrierEvidenceKnown=false)
  return DashboardState(readiness=ReadinessEngine.evaluate(input),quality=QualityEngine.evaluate(QualitySample()),subscriptions=subs,selectedSubscriptionId=subs.singleOrNull()?.id)
 }
}

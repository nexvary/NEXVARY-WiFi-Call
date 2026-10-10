package com.nexvary.wificall.platform.sip

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import com.nexvary.wificall.MainActivity
import com.nexvary.wificall.R
import org.linphone.core.tools.service.CoreService

/** Explicit microphone service; this app does not claim the system dialler role. */
class NexvaryCallService : CoreService() {
    override fun onCreate() {
        super.onCreate()
        active = java.lang.ref.WeakReference(this)
    }
    override fun onDestroy() {
        if (active?.get() === this) active = null
        super.onDestroy()
    }
    companion object {
        private var active: java.lang.ref.WeakReference<NexvaryCallService>? = null
        fun refreshNotification() { active?.get()?.showForegroundServiceNotification(false) }
    }
    override fun createServiceNotificationChannel() {
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel("nexvary_calls", getString(R.string.call_center), NotificationManager.IMPORTANCE_LOW))
    }
    override fun showForegroundServiceNotification(isVideoCall: Boolean) {
        val intent = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val notification = Notification.Builder(this, "nexvary_calls")
            .setSmallIcon(android.R.drawable.sym_call_incoming)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.sip_service_running))
            .setVisibility(Notification.VISIBILITY_PRIVATE)
            .setContentIntent(intent).setOngoing(true)
            .addAction(Notification.Action.Builder(null, getString(if (SipClient.get(this).state.value.muted) R.string.sip_unmute else R.string.sip_mute), action(SipCallActionReceiver.MUTE, 18)).build())
            .addAction(Notification.Action.Builder(null, getString(R.string.sip_hangup), action(SipCallActionReceiver.END, 19)).build())
            .build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(17, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        else startForeground(17, notification)
    }
    private fun action(name: String, request: Int) = PendingIntent.getBroadcast(this, request,
        Intent(this, SipCallActionReceiver::class.java).setAction(name),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
}

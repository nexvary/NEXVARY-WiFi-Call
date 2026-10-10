package com.nexvary.wificall.platform.sip

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Only explicit immutable notification intents can reach this private receiver. */
class SipCallActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != END && intent.action != MUTE) return
        if (!NexvaryCallService.acceptsAction(intent.getStringExtra(TOKEN))) return
        val client = SipClient.get(context)
        val state = client.state.value
        if (!state.accountConfigured || state.call !in setOf(SipCallPhase.DIALLING,
                SipCallPhase.RINGING, SipCallPhase.INCOMING, SipCallPhase.CONNECTED,
                SipCallPhase.MEDIA_ACTIVE)) return
        if (intent.action == END) client.hangUp()
        else if (state.call == SipCallPhase.MEDIA_ACTIVE && state.srtpActive) {
            client.toggleMute()
            NexvaryCallService.refreshNotification()
        }
    }
    companion object {
        const val END = "com.nexvary.wificall.CALL_END"
        const val MUTE = "com.nexvary.wificall.CALL_MUTE"
        const val TOKEN = "call_token"
    }
}

package com.nexvary.wificall.platform.sip

import android.Manifest
import android.app.Notification
import android.app.NotificationManager
import android.graphics.Bitmap
import android.os.Build
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.nexvary.wificall.MainActivity
import com.nexvary.wificall.R
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.linphone.core.Core
import org.linphone.core.Call
import org.linphone.core.CoreListenerStub
import org.linphone.core.MediaEncryption
import org.linphone.core.Account
import org.linphone.core.RegistrationState
import java.io.File
import java.security.cert.CertificateFactory

/** Explicit, isolated CI fixture only. Never included in the ordinary UI suite.
 * Executes the production SipClient; no substitute registration/call implementation.
 * Temporary trust is installed only on this test's Core, with certificate and CN
 * validation still enabled. No global trust store or production source is changed.
 */
class SipGatewayE2ETest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private var phase = "setup"

    @Test fun androidRegistersAndCallsAsteriskWithSrtpBothDirections() {
        val result = JSONObject().put("synthetic", true).put("android_tested", true)
            .put("cellular_tested", false).put("physical_audio_tested", false)
            .put("passed", false).put("success", false).put("fixture_ca_scope", "test_core_only")
            .put("certificate_validation", true).put("hostname_validation", true)
        var client: SipClient? = null
        var engine: Core? = null
        val callEvents = org.json.JSONArray()
        val registrationEvents = org.json.JSONArray()
        val diagnosticListener = object : CoreListenerStub() {
            override fun onAccountRegistrationStateChanged(core: Core, account: Account, state: RegistrationState, message: String) {
                if (registrationEvents.length() < 50) registrationEvents.put(state.name)
            }
            override fun onCallStateChanged(core: Core, call: Call, state: Call.State, message: String) {
                // All fields are enums or numeric measurements. Never record message,
                // remote address, SDP, credentials, or ErrorInfo.phrase.
                if (callEvents.length() < 50) {
                    val stats = call.audioStats
                    callEvents.put(JSONObject().put("state", state.name)
                        .put("media_encryption", call.currentParams.mediaEncryption.name)
                        .put("reason", call.reason.name)
                        .put("sip_status", call.errorInfo.protocolCode)
                        .put("ice_state", stats?.iceState?.name ?: "no_audio_stats"))
                }
            }
        }
        try {
            val fixtureFile = File(context.filesDir, "nexvary-sip-e2e.json")
            check(fixtureFile.isFile && fixtureFile.length() in 1..16384) { "E2E_FIXTURE_REQUIRED" }
            val fixture = JSONObject(fixtureFile.readText())
            val host = fixture.getString("host")
            val port = fixture.getInt("port")
            val username = fixture.getString("username")
            val password = fixture.getString("password")
            val peer = fixture.getString("peer")
            val rootCa = fixture.getString("root_ca")
            // Parse the actual ephemeral CA instead of accepting an arbitrary trust string.
            CertificateFactory.getInstance("X.509").generateCertificate(rootCa.byteInputStream())
            val timeout = fixture.optInt("deadline_seconds", 90).coerceIn(30, 120) * 1000L
            instrumentation.uiAutomation.grantRuntimePermission(context.packageName, Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= 33) instrumentation.uiAutomation.grantRuntimePermission(context.packageName, Manifest.permission.POST_NOTIFICATIONS)
            compose.onNodeWithTag("nav-settings").performClick()
            compose.onNodeWithText(context.getString(R.string.call_center)).performScrollTo().performClick()
            compose.waitForIdle()
            val sip = SipClient.get(context)
            client = sip
            main {
                sip.register(host, port, username, password)
                // Reflection accesses our own class only, never Android hidden APIs.
                val field = SipClient::class.java.getDeclaredField("core").apply { isAccessible = true }
                engine = checkNotNull(field.get(sip) as? Core)
                checkNotNull(engine).addListener(diagnosticListener)
                checkNotNull(engine).setRootCaData(rootCa)
                checkNotNull(engine).verifyServerCertificates(true)
                checkNotNull(engine).verifyServerCn(true)
                checkNotNull(engine).refreshRegisters()
            }
            phase = "registration"
            await(timeout) { sip.state.value.registration == SipRegistration.REGISTERED }
            result.put("tls_registration", true)
            compose.onNodeWithTag("sip-registration").performScrollTo()
            screenshot("registered")

            phase = "outgoing"
            main { sip.dial(peer) }
            phase = "outgoing_media_negotiation"
            await(timeout) { sip.state.value.call == SipCallPhase.MEDIA_ACTIVE && sip.state.value.srtpActive }
            phase = "outgoing_dtmf"
            var invalidDtmfRejected = false
            main {
                try { sip.sendDtmf('A') }
                catch (_: IllegalArgumentException) { invalidDtmfRejected = true }
            }
            check(invalidDtmfRejected) { "INVALID_DTMF_MUST_BE_REJECTED" }
            result.put("invalid_dtmf_rejected", true)
            main { sip.sendDtmf('5') }
            Thread.sleep(500)
            main { sip.sendDtmf('*') }
            result.put("dtmf_requested", org.json.JSONArray().put(5).put(10))
            // The independent host peer must decrypt RFC4733 packets and verify
            // completed event IDs 5,10; local acceptance alone is not receipt proof.
            result.put("dtmf_receive_verification", "independent_peer_evidence_required")
            phase = "outgoing_audio_statistics"
            val outgoing = mediaEvidence(checkNotNull(engine), timeout)
            result.put("outgoing", outgoing)
            phase = "outgoing_screenshot"
            compose.onNodeWithTag("sip-active-call").performScrollTo()
            screenshot("outgoing")

            phase = "outgoing_notification_controls"
            val notifications = context.getSystemService(NotificationManager::class.java)
            await(10000) { notifications.activeNotifications.any { it.id == 17 } }
            val notification = notifications.activeNotifications.single { it.id == 17 }.notification
            check(notification.visibility == Notification.VISIBILITY_PRIVATE) { "CALL_NOTIFICATION_PRIVACY_REQUIRED" }
            check((notification.flags and Notification.FLAG_ONGOING_EVENT) != 0) { "ONGOING_CALL_NOTIFICATION_REQUIRED" }
            val actions = checkNotNull(notification.actions)
            check(actions.size == 2) { "CALL_NOTIFICATION_ACTIONS_REQUIRED" }
            // The dedicated E2E profile runs API35. Do not claim immutable intent
            // verification on older APIs where this public inspection API is absent.
            check(Build.VERSION.SDK_INT >= 31) { "NOTIFICATION_PROOF_REQUIRES_API31" }
            check(actions.all { it.actionIntent.isImmutable } && notification.contentIntent.isImmutable) { "IMMUTABLE_CALL_ACTIONS_REQUIRED" }
            val visibleText = listOf(Notification.EXTRA_TITLE, Notification.EXTRA_TEXT)
                .joinToString(" ") { notification.extras.getCharSequence(it)?.toString().orEmpty() }
            check(listOf(username, peer, host, password).none { visibleText.contains(it) }) { "CALL_NOTIFICATION_MUST_NOT_EXPOSE_ACCOUNT_DATA" }
            actions[0].actionIntent.send()
            await(5000) { sip.state.value.muted }
            actions[0].actionIntent.send()
            await(5000) { !sip.state.value.muted }
            result.put("foreground_notification", JSONObject().put("private_visibility", true)
                .put("immutable_pending_intents", true).put("account_data_redacted", true)
                .put("mute_unmute_actions_verified", true))
            actions[1].actionIntent.send()
            await(20000) { sip.state.value.call == SipCallPhase.IDLE && engine?.currentCall == null }
            result.put("outgoing_hangup", true)
            result.put("notification_end_action", true)
            await(5000) { notifications.activeNotifications.none { it.id == 17 } }
            // Reuse an issued capability after hangup, before the peer may ring.
            // It must neither mute an idle client nor create another call/service.
            actions[0].actionIntent.send()
            instrumentation.waitForIdleSync()
            Thread.sleep(500)
            main { check(!sip.state.value.muted && sip.state.value.call == SipCallPhase.IDLE) { "STALE_NOTIFICATION_ACTION_MUST_BE_REJECTED" } }
            result.put("stale_notification_action_rejected", true)
            export("stage.json", JSONObject().put("ready_for_incoming", true).toString().toByteArray())

            // The authenticated fixture peer originates a separate inbound call after BYE.
            phase = "incoming"
            await(timeout) { sip.state.value.call == SipCallPhase.INCOMING }
            result.put("incoming_ringing", true)
            phase = "incoming_stale_previous_call_actions"
            // Previously issued actions belong to the completed outgoing call.
            // An old End capability must not terminate the new incoming call.
            actions[1].actionIntent.send()
            actions[0].actionIntent.send()
            instrumentation.waitForIdleSync()
            Thread.sleep(500)
            main {
                check(sip.state.value.call == SipCallPhase.INCOMING && !sip.state.value.muted) {
                    "PREVIOUS_CALL_ACTIONS_MUST_NOT_CONTROL_NEW_CALL"
                }
            }
            result.put("previous_call_notification_actions_rejected", true)
            main { sip.answer() }
            phase = "incoming_media_negotiation"
            await(timeout) { sip.state.value.call == SipCallPhase.MEDIA_ACTIVE && sip.state.value.srtpActive }
            phase = "incoming_audio_statistics"
            val incoming = mediaEvidence(checkNotNull(engine), timeout)
            result.put("incoming", incoming)
            compose.onNodeWithTag("sip-active-call").performScrollTo()
            screenshot("incoming")
            main { sip.hangUp() }
            await(20000) { sip.state.value.call == SipCallPhase.IDLE }
            result.put("incoming_hangup", true)

            phase = "gateway_stop_handoff"
            export("stage.json", JSONObject().put("ready_for_gateway_restart", true).toString().toByteArray())
            await(timeout) { restartControl("gateway_stopped") }
            phase = "gateway_registration_loss"
            // Actual TLS connection refusal/loss from stopping the disposable PBX.
            // Never simulate network loss with setNetworkReachable or fake state.
            main { sip.refreshRegistration() }
            await(timeout) { sip.state.value.registration == SipRegistration.FAILED }
            result.put("gateway_loss_observed", true)
            export("stage.json", JSONObject().put("gateway_loss_observed", true).toString().toByteArray())
            phase = "gateway_restart_handoff"
            await(timeout) { restartControl("gateway_restarted") }
            phase = "gateway_reregistration"
            main { sip.refreshRegistration() }
            await(timeout) { sip.state.value.registration == SipRegistration.REGISTERED }
            result.put("gateway_reregistration", true)
            result.put("passed", true)
            result.put("success", true)
        } catch (failure: Throwable) {
            // Class name and a fixed test phase identify assertion/timeouts without
            // exporting potentially sensitive SDK exception messages or stack frames.
            result.put("failure_class", failure.javaClass.simpleName)
            throw failure
        } finally {
            // Only fixed phase codes and measured facts leave the sandbox: no fixture,
            // credential, SDP key, SIP identity or raw native error messages are exported.
            result.put("completed_phase", phase)
            main {
                result.put("call_events", callEvents)
                result.put("registration_events", registrationEvents)
                result.put("last_registration", client?.state?.value?.registration?.name ?: "not_started")
                result.put("last_call_phase", client?.state?.value?.call?.name ?: "not_started")
                result.put("last_srtp_active", client?.state?.value?.srtpActive ?: false)
                engine?.removeListener(diagnosticListener)
            }
            export("result.json", result.toString(2).toByteArray())
            main { client?.disconnect() }
            File(context.filesDir, "nexvary-sip-e2e.json").delete()
            File(context.filesDir, "nexvary-sip-e2e-restart.json").delete()
        }
        assertTrue("ANDROID_SIP_E2E_FAILED", result.getBoolean("passed"))
    }

    private fun mediaEvidence(engine: Core, timeout: Long): JSONObject {
        val started = SystemClock.elapsedRealtime()
        var upload = 0f
        var download = 0f
        var encrypted = false
        await(timeout) {
            val call = engine.currentCall
            encrypted = call?.currentParams?.mediaEncryption == MediaEncryption.SRTP
            val stats = call?.audioStats
            upload = maxOf(upload, stats?.uploadBandwidth ?: 0f)
            download = maxOf(download, stats?.downloadBandwidth ?: 0f)
            encrypted && upload > 0f && download > 0f && SystemClock.elapsedRealtime() - started >= 8000
        }
        return JSONObject().put("media_encryption", "SRTP")
            .put("srtp_negotiated", encrypted).put("positive_upload_bandwidth", upload > 0f)
            .put("positive_download_bandwidth", download > 0f)
            .put("max_upload_kbit_s", upload.toDouble()).put("max_download_kbit_s", download.toDouble())
            .put("observed_duration_ms", SystemClock.elapsedRealtime() - started)
    }

    private fun main(block: () -> Unit) = instrumentation.runOnMainSync(block)

    private fun restartControl(key: String): Boolean {
        check(key in setOf("gateway_stopped", "gateway_restarted"))
        val control = File(context.filesDir, "nexvary-sip-e2e-restart.json")
        if (!control.isFile || control.length() !in 1..4096) return false
        // Host writes a tiny private fixture marker. A partial write is retried;
        // it must never be interpreted as a successful stop or restart.
        return try { JSONObject(control.readText()).optBoolean(key, false) }
        catch (_: org.json.JSONException) { false }
    }

    private fun await(timeout: Long, condition: () -> Boolean) {
        val deadline = SystemClock.elapsedRealtime() + timeout
        while (SystemClock.elapsedRealtime() < deadline) {
            var ready = false
            main { ready = condition() }
            if (ready) return
            Thread.sleep(100)
        }
        error("E2E_TIMEOUT_$phase")
    }

    private fun screenshot(name: String) {
        compose.waitForIdle()
        Thread.sleep(300)
        val bitmap = checkNotNull(instrumentation.uiAutomation.takeScreenshot())
        val bytes = java.io.ByteArrayOutputStream().use {
            check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it))
            it.toByteArray()
        }
        bitmap.recycle()
        export("$name.png", bytes)
    }

    private fun export(name: String, bytes: ByteArray) {
        check(name in setOf("result.json", "stage.json", "registered.png", "outgoing.png", "incoming.png"))
        val file = File(context.getExternalFilesDir("sip-e2e"), name)
        file.parentFile!!.mkdirs()
        file.writeBytes(bytes)
        fun shell(command: String) {
            val output = ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(command))
                .use { it.readBytes().toString(Charsets.UTF_8) }
            check(output.isBlank()) { "E2E_EVIDENCE_EXPORT_FAILED" }
        }
        shell("mkdir -p /sdcard/Download/NEXVARY-SIP-E2E")
        shell("cp ${file.absolutePath} /sdcard/Download/NEXVARY-SIP-E2E/$name")
    }
}

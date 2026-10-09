package com.nexvary.wificall.platform.sip

import android.Manifest
import android.graphics.Bitmap
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
        val diagnosticListener = object : CoreListenerStub() {
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
            phase = "outgoing_audio_statistics"
            val outgoing = mediaEvidence(checkNotNull(engine), timeout)
            result.put("outgoing", outgoing)
            phase = "outgoing_screenshot"
            compose.onNodeWithTag("sip-active-call").performScrollTo()
            screenshot("outgoing")
            main { sip.hangUp() }
            await(20000) { sip.state.value.call == SipCallPhase.IDLE && engine?.currentCall == null }
            result.put("outgoing_hangup", true)
            export("stage.json", JSONObject().put("ready_for_incoming", true).toString().toByteArray())

            // The authenticated fixture peer originates a separate inbound call after BYE.
            phase = "incoming"
            await(timeout) { sip.state.value.call == SipCallPhase.INCOMING }
            result.put("incoming_ringing", true)
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
                result.put("last_registration", client?.state?.value?.registration?.name ?: "not_started")
                result.put("last_call_phase", client?.state?.value?.call?.name ?: "not_started")
                result.put("last_srtp_active", client?.state?.value?.srtpActive ?: false)
                engine?.removeListener(diagnosticListener)
            }
            export("result.json", result.toString(2).toByteArray())
            main { client?.disconnect() }
            File(context.filesDir, "nexvary-sip-e2e.json").delete()
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

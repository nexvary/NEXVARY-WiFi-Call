package com.nexvary.wificall.platform.sip

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import com.nexvary.wificall.BuildConfig
import com.nexvary.wificall.core.InternalDialPolicy
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.linphone.core.*

/** All methods are called on Android's main thread, as required by liblinphone auto-iterate. */
class SipClient private constructor(context: Context) {
    companion object {
        @Volatile private var instance: SipClient? = null
        fun get(context: Context): SipClient = instance ?: synchronized(this) {
            instance ?: SipClient(context.applicationContext).also { instance = it }
        }
    }
    private val context = context.applicationContext
    private var core: Core? = null
    private var domain = ""
    private val mutable = MutableStateFlow(SipUiState())
    val state = mutable.asStateFlow()
    private val listener = object : CoreListenerStub() {
        override fun onAccountRegistrationStateChanged(core: Core, account: Account, registration: RegistrationState, message: String) {
            mutable.value = mutable.value.copy(registration = when (registration) {
                RegistrationState.Ok -> SipRegistration.REGISTERED
                RegistrationState.Progress, RegistrationState.Refreshing -> SipRegistration.CONNECTING
                RegistrationState.Failed -> SipRegistration.FAILED
                else -> SipRegistration.OFFLINE
            }, error = if (registration == RegistrationState.Failed) "SIP_REGISTRATION_FAILED" else null)
        }
        override fun onCallStateChanged(core: Core, call: Call, callState: Call.State, message: String) {
            // Raw SIP messages can contain phone numbers and credentials: never log/display message.
            val phase = when (callState) {
                Call.State.IncomingReceived, Call.State.IncomingEarlyMedia -> SipCallPhase.INCOMING
                Call.State.OutgoingInit, Call.State.OutgoingProgress -> SipCallPhase.DIALLING
                Call.State.OutgoingRinging, Call.State.OutgoingEarlyMedia -> SipCallPhase.RINGING
                Call.State.Connected -> SipCallPhase.CONNECTED
                Call.State.StreamsRunning -> SipCallPhase.MEDIA_ACTIVE
                Call.State.End, Call.State.Released -> SipCallPhase.IDLE
                Call.State.Error -> SipCallPhase.FAILED
                else -> mutable.value.call
            }
            val encrypted = call.currentParams.mediaEncryption == MediaEncryption.SRTP
            val finished = callState == Call.State.End || callState == Call.State.Error
            val history = if (finished) (listOf(SipHistoryEntry(call.remoteAddress.username.orEmpty(), call.dir == Call.Dir.Incoming, call.duration, callState == Call.State.Error)) + mutable.value.history).take(30) else mutable.value.history
            mutable.value = mutable.value.copy(call = phase, peer = call.remoteAddress.username.orEmpty(),
                srtpActive = phase == SipCallPhase.MEDIA_ACTIVE && encrypted,
                history = history, error = if (callState == Call.State.Error) "SIP_CALL_FAILED" else null)
        }
    }
    fun register(host: String, port: Int, username: String, password: String, stun: String = "") {
        require(InternalDialPolicy.validHost(host) && InternalDialPolicy.validPort(port)) { "INVALID_SERVER" }
        require(InternalDialPolicy.validExtension(username) && password.length in 8..128) { "INVALID_ACCOUNT" }
        require(stun.isEmpty() || InternalDialPolicy.validHost(stun)) { "INVALID_STUN_SERVER" }
        require(ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) { "MICROPHONE_PERMISSION_REQUIRED" }
        disconnect()
        mutable.value = SipUiState(registration = SipRegistration.CONNECTING)
        try {
            val factory = Factory.instance()
            factory.setDebugMode(false, "NEXVARY")
            factory.loggingService.setLogLevelMask(0)
            // In-memory Config prevents SIP passwords and call details being written to a config file.
            val config = factory.createConfigFromString("[sip]\nstore_auth_info=0\n[storage]\nuri=null\n")
            val engine = factory.createCoreWithConfig(config, context)
            core = engine
            val transports = factory.createTransports()
            transports.udpPort = 0
            transports.tcpPort = 0
            transports.tlsPort = -1
            transports.dtlsPort = 0
            check(engine.setTransports(transports) == 0) { "TLS_TRANSPORT_FAILED" }
            engine.verifyServerCertificates(true)
            engine.verifyServerCn(true)
            engine.setMediaEncryption(MediaEncryption.SRTP)
            engine.isMediaEncryptionMandatory = true
            engine.isVideoCaptureEnabled = false
            engine.isVideoDisplayEnabled = false
            engine.maxCalls = 1
            engine.isPushNotificationEnabled = false
            engine.setUserAgent("NEXVARY-WiFi-Call", BuildConfig.VERSION_NAME)
            val policy = engine.createNatPolicy()
            policy.isIceEnabled = true
            if (stun.isNotEmpty()) { policy.stunServer = stun; policy.isStunEnabled = true }
            engine.natPolicy = policy
            engine.addListener(listener)
            engine.start()
            val identity = factory.createAddress("sip:$username@$host") ?: error("INVALID_IDENTITY")
            val server = factory.createAddress("sip:$host:$port;transport=tls") ?: error("INVALID_PROXY")
            server.setTransport(TransportType.Tls)
            val params = engine.createAccountParams()
            check(params.setIdentityAddress(identity) == 0) { "IDENTITY_REJECTED" }
            check(params.setServerAddress(server) == 0) { "PROXY_REJECTED" }
            params.transport = TransportType.Tls
            params.isRegisterEnabled = true
            params.natPolicy = policy
            params.isOutboundProxyEnabled = true
            engine.addAuthInfo(factory.createAuthInfo(username, null, password, null, null, host))
            val account = engine.createAccount(params)
            engine.addAccount(account)
            engine.defaultAccount = account
            domain = host
        } catch (e: Exception) {
            disconnect()
            mutable.value = mutable.value.copy(registration = SipRegistration.FAILED, error = "SIP_SETUP_FAILED")
            throw IllegalStateException("SIP_SETUP_FAILED")
        }
    }
    fun dial(extension: String) {
        require(InternalDialPolicy.validExtension(extension)) { "INTERNAL_EXTENSION_ONLY" }
        require(mutable.value.registration == SipRegistration.REGISTERED) { "SIP_NOT_REGISTERED" }
        require(mutable.value.call in setOf(SipCallPhase.IDLE, SipCallPhase.FAILED)) { "CALL_BUSY" }
        val engine = checkNotNull(core)
        val target = Factory.instance().createAddress("sip:$extension@$domain;transport=tls") ?: error("INVALID_DESTINATION")
        target.setTransport(TransportType.Tls)
        val params = engine.createCallParams(null) ?: error("CALL_PARAMS_FAILED")
        params.isVideoEnabled = false
        params.isAudioEnabled = true
        params.mediaEncryption = MediaEncryption.SRTP
        checkNotNull(engine.inviteAddressWithParams(target, params)) { "INVITE_FAILED" }
    }
    fun answer() {
        require(mutable.value.call == SipCallPhase.INCOMING) { "NO_INCOMING_CALL" }
        val engine = checkNotNull(core)
        val call = checkNotNull(engine.currentCall)
        val params = engine.createCallParams(call) ?: error("CALL_PARAMS_FAILED")
        params.isVideoEnabled = false
        params.mediaEncryption = MediaEncryption.SRTP
        check(call.acceptWithParams(params) == 0) { "ANSWER_FAILED" }
    }
    fun hangUp() {
        val call = core?.currentCall ?: return
        if (mutable.value.call == SipCallPhase.INCOMING) call.decline(Reason.Declined) else call.terminate()
    }
    fun toggleMute() {
        val muted = !mutable.value.muted
        core?.isMicEnabled = !muted
        mutable.value = mutable.value.copy(muted = muted)
    }
    fun toggleSpeaker() {
        val engine = checkNotNull(core)
        val speaker = !mutable.value.speaker
        val device = engine.audioDevices.firstOrNull { it.type == if (speaker) AudioDevice.Type.Speaker else AudioDevice.Type.Earpiece }
            ?: error("AUDIO_DEVICE_UNAVAILABLE")
        engine.currentCall?.outputAudioDevice = device
        mutable.value = mutable.value.copy(speaker = speaker)
    }
    fun disconnect() {
        core?.let { engine ->
            engine.terminateAllCalls()
            engine.clearAccounts()
            engine.clearAllAuthInfo()
            engine.removeListener(listener)
            engine.stop()
        }
        core = null
        domain = ""
        mutable.value = SipUiState(history = mutable.value.history)
    }
}
enum class SipRegistration { OFFLINE, CONNECTING, REGISTERED, FAILED }
enum class SipCallPhase { IDLE, DIALLING, RINGING, INCOMING, CONNECTED, MEDIA_ACTIVE, FAILED }
data class SipHistoryEntry(val extension: String, val incoming: Boolean, val seconds: Int, val failed: Boolean)
data class SipUiState(val registration: SipRegistration = SipRegistration.OFFLINE, val call: SipCallPhase = SipCallPhase.IDLE,
    val peer: String = "", val srtpActive: Boolean = false, val muted: Boolean = false, val speaker: Boolean = false,
    val error: String? = null, val history: List<SipHistoryEntry> = emptyList())

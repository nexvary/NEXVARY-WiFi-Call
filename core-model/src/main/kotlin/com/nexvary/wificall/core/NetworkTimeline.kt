package com.nexvary.wificall.core

enum class NetworkEventType { AVAILABLE, CAPABILITIES_CHANGED, LINK_CHANGED, LOST }

data class NetworkContext(
    val wifi: Boolean,
    val validated: Boolean,
    val captivePortal: Boolean,
    val vpn: Boolean,
    val metered: Boolean,
    val downstreamKbps: Int?,
    val dnsServerCount: Int?
)

data class NetworkEvent(
    val sequence: Long,
    val type: NetworkEventType,
    val context: NetworkContext?
)

class NetworkTimeline(private val maxEvents: Int = 50) {
    init { require(maxEvents in 1..500) }
    private val events = ArrayDeque<NetworkEvent>()
    fun add(event: NetworkEvent) {
        events.addLast(event)
        while (events.size > maxEvents) events.removeFirst()
    }
    fun snapshot(): List<NetworkEvent> = events.toList()
}

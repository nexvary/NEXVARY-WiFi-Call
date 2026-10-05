package com.nexvary.wificall.core
import kotlin.test.*
class NetworkTimelineTest {
 @Test fun retentionIsBounded(){
   val t=NetworkTimeline(2)
   t.add(NetworkEvent(1,NetworkEventType.AVAILABLE,null))
   t.add(NetworkEvent(2,NetworkEventType.LINK_CHANGED,null))
   t.add(NetworkEvent(3,NetworkEventType.LOST,null))
   assertEquals(listOf(2L,3L),t.snapshot().map{it.sequence})
 }
}

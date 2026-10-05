package com.nexvary.wificall.core
import kotlin.test.*
class ChangeAndPrivacyTest {
 @Test fun explainsVpnAndValidationChange(){
  val a=NetworkContext(true,true,false,false,false,null,2); val b=NetworkContext(true,false,false,true,false,null,2)
  val r=ChangeExplainer.compare(a,b).reasons
  assertTrue(ChangeReason.VPN_ENABLED in r); assertTrue(ChangeReason.VALIDATION_LOST in r)
 }
 @Test fun redactsSensitiveText(){
  val x=DiagnosticRedactor.redact("imsi 310260123456789 ip 192.168.1.8 phone +201001234567")
  assertFalse(x.contains("310260123456789")); assertFalse(x.contains("192.168.1.8")); assertFalse(x.contains("201001234567"))
 }
}

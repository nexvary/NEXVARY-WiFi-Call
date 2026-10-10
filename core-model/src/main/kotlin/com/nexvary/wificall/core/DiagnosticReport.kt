package com.nexvary.wificall.core

data class DiagnosticReport(val readiness:ReadinessResult,val quality:QualityResult,val evidence:EvidenceLevel,val entitlement:EntitlementState,val notes:List<String>)
object DiagnosticReportFormatter { fun redactedText(r:DiagnosticReport):String=DiagnosticRedactor.redact(buildString{appendLine("readiness="+r.readiness.state);appendLine("path="+r.readiness.path);appendLine("quality="+r.quality.grade);appendLine("evidence="+r.evidence);appendLine("entitlement="+r.entitlement);r.notes.forEach{appendLine("note="+it)}}) }

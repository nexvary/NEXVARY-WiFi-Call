package com.nexvary.wificall.core

enum class QualityGrade { EXCELLENT, GOOD, FAIR, POOR, UNKNOWN }

data class QualitySample(
    val latencyMs: Double? = null,
    val variabilityMs: Double? = null,
    val lossPercent: Double? = null
)

data class QualityResult(val score: Int?, val grade: QualityGrade, val reasons: List<String>)

object QualityEngine {
    fun evaluate(s: QualitySample): QualityResult {
        if (s.latencyMs == null && s.variabilityMs == null && s.lossPercent == null)
            return QualityResult(null, QualityGrade.UNKNOWN, listOf("NO_MEASUREMENTS"))
        var score = 100
        val reasons = mutableListOf<String>()
        s.latencyMs?.let {
            when { it > 300 -> { score -= 45; reasons += "HIGH_LATENCY" }
                   it > 150 -> { score -= 25; reasons += "ELEVATED_LATENCY" }
                   it > 80 -> score -= 10 }
        }
        s.variabilityMs?.let {
            when { it > 50 -> { score -= 30; reasons += "HIGH_VARIABILITY" }
                   it > 30 -> { score -= 18; reasons += "ELEVATED_VARIABILITY" }
                   it > 15 -> score -= 8 }
        }
        s.lossPercent?.let {
            when { it > 5 -> { score -= 45; reasons += "HIGH_LOSS" }
                   it > 2 -> { score -= 25; reasons += "ELEVATED_LOSS" }
                   it > 0.5 -> score -= 10 }
        }
        score = score.coerceIn(0, 100)
        val grade = when { score >= 90 -> QualityGrade.EXCELLENT; score >= 75 -> QualityGrade.GOOD; score >= 55 -> QualityGrade.FAIR; else -> QualityGrade.POOR }
        return QualityResult(score, grade, reasons)
    }
}

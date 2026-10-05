package com.nexvary.wificall.core
import kotlin.test.*
class QualityTest {
 @Test fun noMeasurementsIsUnknown(){ assertEquals(QualityGrade.UNKNOWN, QualityEngine.evaluate(QualitySample()).grade) }
 @Test fun cleanNetworkScoresExcellent(){ assertEquals(QualityGrade.EXCELLENT, QualityEngine.evaluate(QualitySample(35.0,5.0,0.0)).grade) }
 @Test fun severeLossIsPoor(){ assertEquals(QualityGrade.POOR, QualityEngine.evaluate(QualitySample(200.0,40.0,8.0)).grade) }
}

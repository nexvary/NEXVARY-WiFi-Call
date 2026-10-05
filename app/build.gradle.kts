plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}
android {
    namespace = "com.nexvary.wificall"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.nexvary.wificall"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0-alpha01"
    }
    buildFeatures { compose = true }
}
dependencies {
    implementation(project(":core-model"))
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.10.0")
    val composeBom = platform("androidx.compose:compose-bom:2026.09.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
}
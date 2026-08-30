plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.mobde3.creator"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.mobde3.creator"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        // عنوان الخادم يُضبط عند البناء، ولا يُكتب في الكود
        buildConfigField("String", "API_BASE_URL", "\"${providers.gradleProperty("apiBaseUrl").getOrElse("http://10.0.2.2:8000")}\"")
        // بصمات توقيع حزم TikTok — تُملأ بعد رصدها على جهاز حقيقي
        buildConfigField("String", "TIKTOK_SIGNATURES", "\"${providers.gradleProperty("tiktokSignatures").getOrElse("")}\"")
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    buildTypes {
        release { isMinifyEnabled = false }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")

    implementation("androidx.core:core-ktx:1.15.0")
    // تخزين مشفَّر لرموز الجلسة
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.navigation:navigation-compose:2.8.5")

    // رقم الهاتف بلا كتابة، وقراءة رمز التحقق آليًا
    implementation("com.google.android.gms:play-services-auth:21.3.0")
    implementation("com.google.android.gms:play-services-auth-api-phone:18.1.0")
    // سلامة الجهاز
    implementation("com.google.android.play:integrity:1.4.0")
    // إشعارات المبدع
    implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    implementation("com.google.firebase:firebase-messaging")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    // TikTok Login Kit — يُفعَّل بعد تسجيل التطبيق واعتماد النطاقات
    // implementation("com.bytedance.ies.ugc.aweme:opensdk-oversea-external:<version>")
}

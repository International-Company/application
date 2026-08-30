pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        // مستودع TikTok Login Kit — يُضاف عند ربط الـ SDK فعليًا
        // maven { url = uri("https://artifact.bytedance.com/repository/AwemeOpenSDK") }
    }
}

rootProject.name = "Mobde3"
include(":app")

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "br.com.frotaweb.oscorretiva"
    compileSdk = 35

    defaultConfig {
        applicationId = "br.com.frotaweb.oscorretiva"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }
}

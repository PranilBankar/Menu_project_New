plugins {
    id("com.android.application")
    id("kotlin-android")
    id("dev.flutter.flutter-gradle-plugin") // Required to recognize 'flutter.'
}

android {
    // This 'namespace' is now required in modern Gradle
    namespace = "com.example.menu_intelligence" 
    compileSdk = flutter.compileSdkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        // Use string assignment for jvmTarget in KTS
        jvmTarget = "17" 
    }

    defaultConfig {
        applicationId = "com.example.menu_intelligence"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        getByName("release") {
            // KTS requires getByName for existing build types
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

// Keep the flutter block at the bottom, outside the android block
flutter {
    source = "../.."
}
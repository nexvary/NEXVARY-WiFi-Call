pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral(); maven { url = uri("https://download.linphone.org/releases/maven_repository/"); content { includeGroup("org.linphone") } } } }
rootProject.name = "NEXVARY-WiFi-Call"
include(":app", ":core-model")

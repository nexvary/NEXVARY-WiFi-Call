# liblinphone SDK licensing and distribution

Dependency: `org.linphone:linphone-sdk-android:5.4.100` (pinned).
Copyright: Belledonne Communications and respective component authors.

The exact 5.4.100 official Maven POM declares **GNU General Public License v3.0**:
https://download.linphone.org/releases/maven_repository/org/linphone/linphone-sdk-android/5.4.100/linphone-sdk-android-5.4.100.pom

Official source:
https://gitlab.linphone.org/BC/public/linphone-sdk

GPLv3 license:
https://www.gnu.org/licenses/gpl-3.0.html

The current vendor licensing page describes an AGPLv3/commercial dual-license
model. Inspection of the exact 5.4.100 sources JAR also found an AGPLv3-or-later
header in `org/linphone/core/tools/service/CoreService.java`, which this app
subclasses. The Maven label therefore does not establish a uniform GPL-only
license for every SDK component. Component notices take precedence over a
single aggregate POM label:
https://www.linphone.org/en/liblinphone-voip-sdk/

This integration does not silently relicense this application's existing source.
Public distribution of a linked APK requires a compatible license for the
application, corresponding source and notices for the complete SDK/components,
or a valid vendor commercial license. The APK is a development pilot, not a
license-cleared proprietary commercial release. Do not remove vendor/component
notices when packaging. Native component license inventory and corresponding
source bundle must be completed before public release.

Official Android integration/service/audio-focus documentation:
https://wiki.linphone.org/xwiki/wiki/public/view/Lib/Getting%20started/Android/

Exact inspected source artifact: https://download.linphone.org/releases/maven_repository/org/linphone/linphone-sdk-android/5.4.100/linphone-sdk-android-5.4.100-sources.jar

AGPLv3 text: https://www.gnu.org/licenses/agpl-3.0.html

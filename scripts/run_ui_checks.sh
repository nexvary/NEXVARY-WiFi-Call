#!/usr/bin/env bash
set -uo pipefail
# AGP uninstalls the test application and deletes its external-files directory.
# Shell-owned Download screenshots survive that cleanup, including failed tests.
collect_screenshots() {
    adb pull /sdcard/Download/NEXVARY-WiFi-Call-screenshots ui-screenshots || true
}
trap collect_screenshots EXIT
gradle :app:connectedDebugAndroidTest --stacktrace

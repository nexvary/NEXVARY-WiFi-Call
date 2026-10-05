#!/usr/bin/env bash
set -uo pipefail
# AGP removes app-owned files after instrumentation; keep shell-owned copies.
collect_screenshots() {
    local test_status=$?
    trap - EXIT
    if ! adb pull /sdcard/Download/NEXVARY-WiFi-Call-screenshots ui-screenshots; then
        if [ "$test_status" -eq 0 ]; then test_status=1; fi
    fi
    if [ "$test_status" -eq 0 ] && ! compgen -G 'ui-screenshots/*.png' > /dev/null; then
        echo "UI screenshots were not collected" >&2
        test_status=1
    fi
    exit "$test_status"
}
trap collect_screenshots EXIT
gradle :app:connectedDebugAndroidTest --stacktrace

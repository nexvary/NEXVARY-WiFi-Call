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
    if [ "$test_status" -eq 0 ]; then
        for locale in ar en tr es de it fr; do
            for page in home diagnostics diagnostics-lab diagnostics-audio sims sims-selected about settings call-center sip-dialler; do
                if [ ! -s "ui-screenshots/$locale-$page.png" ]; then
                    echo "Missing screenshot: $locale-$page.png" >&2
                    test_status=1
                fi
            done
        done
        for name in ar-activity-home en-activity-home installed-launcher-icon activity-landscape activity-portrait; do
            if [ ! -s "ui-screenshots/$name.png" ]; then
                echo "Missing screenshot: $name.png" >&2
                test_status=1
            fi
        done
    fi
    exit "$test_status"
}
trap collect_screenshots EXIT
adb shell rm -rf /sdcard/Download/NEXVARY-WiFi-Call-screenshots
gradle :app:connectedDebugAndroidTest --stacktrace \
    -Pandroid.testInstrumentationRunnerArguments.notClass=com.nexvary.wificall.platform.sip.SipGatewayE2ETest

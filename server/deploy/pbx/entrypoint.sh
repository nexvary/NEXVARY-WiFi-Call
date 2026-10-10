#!/bin/sh
set -eu
for required in pjsip.conf extensions.conf rtp.conf modules.conf; do
    test -r "/nexvary-config/$required" || { echo "Missing readable private PBX configuration" >&2; exit 1; }
done
test -r /etc/asterisk/tls/fullchain.pem
test -r /etc/asterisk/tls/privkey.pem
test -r /usr/share/asterisk/documentation/core-en_US.xml
module_file=$(dpkg-query -L asterisk-modules | awk '/\/res_pjsip\.so$/ && !found { path=$0; found=1 } END { print path }')
test -n "$module_file"
test -r "$module_file"
module_directory=$(dirname "$module_file")
# Runtime file lives only in the private tmpfs, never on the host /etc.
cat > /run/asterisk/asterisk.conf <<CONF
[directories]
astetcdir => /nexvary-config
astmoddir => $module_directory
astvarlibdir => /var/lib/asterisk
astdbdir => /var/lib/nexvary-pbx
astkeydir => /etc/asterisk/tls
astdatadir => /usr/share/asterisk
astagidir => /var/spool/asterisk
astspooldir => /var/spool/asterisk
astrundir => /run/asterisk
astlogdir => /var/log/asterisk
[options]
verbose = 0
debug = 0
CONF
exec asterisk -f -C /run/asterisk/asterisk.conf

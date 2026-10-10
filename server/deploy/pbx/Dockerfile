ARG NEXVARY_BASE_IMAGE=ubuntu:24.04
FROM ${NEXVARY_BASE_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
    && chmod 755 /usr/sbin/policy-rc.d \
    && apt-get update \
    && apt-get install -y --no-install-recommends asterisk asterisk-modules ca-certificates \
    && asterisk -V | grep -q 'Asterisk 20\.' \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 nexvary \
    && useradd --uid 10001 --gid 10001 --no-create-home nexvary \
    && mkdir -p /run/asterisk /var/log/asterisk /var/spool/asterisk /var/lib/nexvary-pbx /etc/asterisk/tls \
    && chown -R 10001:10001 /run/asterisk /var/log/asterisk /var/spool/asterisk /var/lib/nexvary-pbx
COPY entrypoint.sh /usr/local/bin/nexvary-pbx
RUN chmod 755 /usr/local/bin/nexvary-pbx
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/nexvary-pbx"]

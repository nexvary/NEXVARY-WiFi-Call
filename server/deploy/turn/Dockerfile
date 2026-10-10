FROM ubuntu:24.04
ARG COTURN_VERSION=4.6.1-1build4
ENV DEBIAN_FRONTEND=noninteractive
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
    && chmod 755 /usr/sbin/policy-rc.d \
    && apt-get update \
    && apt-get install -y --no-install-recommends coturn=${COTURN_VERSION} ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10002 nexvary-turn \
    && useradd --uid 10002 --gid 10002 --no-create-home nexvary-turn \
    && mkdir -p /run/nexvary-turn /etc/nexvary-turn/tls
USER 10002:10002
ENTRYPOINT ["turnserver", "-c", "/nexvary-config/turnserver.conf"]

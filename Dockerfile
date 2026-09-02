FROM debian:bookworm-slim

ARG NASDROP_VERSION=0.9.4
ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="NASDrop" \
      org.opencontainers.image.description="Self-hosted direct-to-storage download portal" \
      org.opencontainers.image.source="https://github.com/littleweirdlab0514-web/NASDROP" \
      org.opencontainers.image.version="${NASDROP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="MIT"

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       gosu \
       nodejs \
       python3 \
       7zip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend.py gofile_wt.mjs LICENSE THIRD_PARTY_NOTICES.md ./
COPY synology/web ./synology/web
COPY docker/account.py /app/docker/account.py
COPY docker/entrypoint.sh /usr/local/bin/nasdrop-entrypoint
COPY docker/account-command.sh /usr/local/bin/nasdrop-account

RUN chmod 0755 /usr/local/bin/nasdrop-entrypoint /usr/local/bin/nasdrop-account \
    && mkdir -p /config /downloads \
    && python3 -m py_compile /app/backend.py /app/docker/account.py \
    && node --check /app/gofile_wt.mjs \
    && 7zz >/dev/null

ENV NAS_PORTAL_STATE_DIR=/config \
    NAS_PORTAL_STATIC_DIR=/app/synology/web \
    NAS_PORTAL_NAS_TARGET=/downloads \
    NAS_PORTAL_STORAGE_ROOTS=/downloads \
    NAS_PORTAL_LISTEN_HOST=0.0.0.0 \
    NAS_PORTAL_LISTEN_PORT=8791 \
    NAS_PORTAL_LAUNCHER_PORT=8791 \
    NAS_PORTAL_7ZZ=/usr/bin/7zz \
    NAS_PORTAL_VERSION=${NASDROP_VERSION} \
    NAS_PORTAL_DOWNLOAD_MODE=segmented \
    NAS_PORTAL_AUTO_EXTRACT_ARCHIVES=true \
    NAS_PORTAL_DISK_PROTECTION=true \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOME=/config \
    TZ=UTC \
    PUID=1000 \
    PGID=1000

EXPOSE 8791
VOLUME ["/config", "/downloads"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl --fail --silent --show-error http://127.0.0.1:8791/api/auth/status >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/nasdrop-entrypoint"]
CMD ["python3", "/app/backend.py"]

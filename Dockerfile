FROM debian:trixie-slim

ARG NASDROP_VERSION=0.9.25
ARG VCS_REF=unknown
ARG TARGETARCH
ARG SEVENZIP_VERSION=2603
ARG SEVENZIP_SHA256_AMD64=dc99eff5008f1ab79bd7084c68513701547a808a89502bf4133683535ab3c695
ARG SEVENZIP_SHA256_ARM64=2389ba20e4d8295e8709c20b6263b69bd1ec4972fe38a04ad7a1badbf595b996

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
       tzdata \
       xz-utils \
    && case "${TARGETARCH:-$(dpkg --print-architecture)}" in \
         amd64) sevenzip_arch=x64; sevenzip_sha256="$SEVENZIP_SHA256_AMD64" ;; \
         arm64) sevenzip_arch=arm64; sevenzip_sha256="$SEVENZIP_SHA256_ARM64" ;; \
         *) echo "Unsupported Docker architecture: ${TARGETARCH:-$(dpkg --print-architecture)}" >&2; exit 64 ;; \
       esac \
    && curl --fail --location --silent --show-error \
       "https://github.com/ip7z/7zip/releases/download/26.03/7z${SEVENZIP_VERSION}-linux-${sevenzip_arch}.tar.xz" \
       --output /tmp/7zip.tar.xz \
    && echo "${sevenzip_sha256}  /tmp/7zip.tar.xz" | sha256sum --check --strict - \
    && mkdir -p /tmp/7zip /usr/share/doc/7zip \
    && tar -xJf /tmp/7zip.tar.xz -C /tmp/7zip 7zz License.txt \
    && install -m 0755 /tmp/7zip/7zz /usr/local/bin/7zz \
    && install -m 0644 /tmp/7zip/License.txt /usr/share/doc/7zip/License.txt \
    && rm -rf /tmp/7zip /tmp/7zip.tar.xz /var/lib/apt/lists/*

WORKDIR /app

COPY backend.py transfer_parts.py gofile_wt.mjs LICENSE THIRD_PARTY_NOTICES.md ./
COPY synology/web ./synology/web
COPY docker/account.py /app/docker/account.py
COPY docker/entrypoint.sh /usr/local/bin/nasdrop-entrypoint
COPY docker/account-command.sh /usr/local/bin/nasdrop-account

# Release ZIPs can preserve owner-only source modes. Normalize the files copied
# into the image so the configured non-root PUID can import and serve them.
RUN sed -i 's/\r$//' /usr/local/bin/nasdrop-entrypoint /usr/local/bin/nasdrop-account \
    && chmod 0755 /usr/local/bin/nasdrop-entrypoint /usr/local/bin/nasdrop-account \
    && chmod -R a+rX /app \
    && mkdir -p /config /downloads \
    && python3 -m py_compile /app/backend.py /app/docker/account.py \
    && node --check /app/gofile_wt.mjs \
    && 7zz i > /tmp/7zip-formats \
    && grep -q ' Rar ' /tmp/7zip-formats \
    && grep -q ' Rar5 ' /tmp/7zip-formats \
    && rm /tmp/7zip-formats

ENV NAS_PORTAL_STATE_DIR=/config \
    NAS_PORTAL_STATIC_DIR=/app/synology/web \
    NAS_PORTAL_NAS_TARGET=/downloads \
    NAS_PORTAL_STORAGE_ROOTS=/downloads \
    NAS_PORTAL_LISTEN_HOST=0.0.0.0 \
    NAS_PORTAL_LISTEN_PORT=8791 \
    NAS_PORTAL_LAUNCHER_PORT=8791 \
    NAS_PORTAL_7ZZ=/usr/local/bin/7zz \
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

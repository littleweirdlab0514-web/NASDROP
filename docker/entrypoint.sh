#!/bin/sh
set -eu

case "${PUID:-}" in
  ''|*[!0-9]*) echo "NASDrop: PUID must be a numeric user ID." >&2; exit 64 ;;
esac
case "${PGID:-}" in
  ''|*[!0-9]*) echo "NASDrop: PGID must be a numeric group ID." >&2; exit 64 ;;
esac

state_dir=${NAS_PORTAL_STATE_DIR:-/config}
target_dir=${NAS_PORTAL_NAS_TARGET:-}
export NAS_PORTAL_SERVICE_USER="PUID ${PUID} / PGID ${PGID}"

mkdir -p "$state_dir"
chown "${PUID}:${PGID}" "$state_dir"
chmod 0700 "$state_dir"

if [ -n "$target_dir" ]; then
  if [ ! -d "$target_dir" ]; then
    echo "NASDrop: warning: download target does not exist: $target_dir" >&2
  elif ! gosu "${PUID}:${PGID}" test -r "$target_dir" || ! gosu "${PUID}:${PGID}" test -w "$target_dir"; then
    echo "NASDrop: warning: PUID ${PUID} / PGID ${PGID} cannot read and write $target_dir." >&2
    echo "NASDrop: adjust the host folder permission or choose another mounted folder in Settings." >&2
  fi
fi

if [ "${1:-}" = "account" ]; then
  shift
  exec gosu "${PUID}:${PGID}" python3 /app/docker/account.py "$@"
fi

exec gosu "${PUID}:${PGID}" "$@"

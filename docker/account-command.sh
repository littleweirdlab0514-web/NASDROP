#!/bin/sh
set -eu

case "${PUID:-}" in
  ''|*[!0-9]*) echo "NASDrop: PUID must be a numeric user ID." >&2; exit 64 ;;
esac
case "${PGID:-}" in
  ''|*[!0-9]*) echo "NASDrop: PGID must be a numeric group ID." >&2; exit 64 ;;
esac

exec gosu "${PUID}:${PGID}" python3 /app/docker/account.py "$@"

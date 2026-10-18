#!/bin/sh
set -eu

umask 077

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -n "${NASDROP_COMPOSE_FILE:-}" ]; then
  compose_file=$NASDROP_COMPOSE_FILE
elif [ -f "$script_dir/compose.release.yaml" ]; then
  compose_file="$script_dir/compose.release.yaml"
else
  compose_file="$script_dir/compose.yaml"
fi
update_file=${NASDROP_UPDATE_COMPOSE_FILE:-"$script_dir/compose.auto-update.yaml"}
project_dir=${NASDROP_COMPOSE_PROJECT_DIR:-"$script_dir"}
target_image=${NASDROP_AUTO_UPDATE_IMAGE:-ghcr.io/littleweirdlab0514-web/nasdrop:latest}
timeout=${NASDROP_UPDATE_TIMEOUT:-180}
backup_dir=${NASDROP_UPDATE_BACKUP_DIR:-"$project_dir/nasdrop-update-backups"}
lock_dir="$project_dir/.nasdrop-update.lock"

case "$timeout" in
  ''|*[!0-9]*) echo "NASDrop update: NASDROP_UPDATE_TIMEOUT must be a positive integer." >&2; exit 64 ;;
esac
[ "$timeout" -gt 0 ] || { echo "NASDrop update: NASDROP_UPDATE_TIMEOUT must be greater than zero." >&2; exit 64; }

command -v docker >/dev/null 2>&1 || { echo "NASDrop update: docker was not found." >&2; exit 69; }
[ -f "$compose_file" ] || { echo "NASDrop update: missing $compose_file" >&2; exit 66; }
[ -f "$update_file" ] || { echo "NASDrop update: missing $update_file" >&2; exit 66; }

if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "NASDrop update: another update is already running." >&2
  exit 75
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT HUP INT TERM

compose() {
  selected_image=$1
  pull_policy=$2
  shift 2
  NASDROP_UPDATE_IMAGE="$selected_image" NASDROP_UPDATE_PULL_POLICY="$pull_policy" \
    docker compose --project-directory "$project_dir" -f "$compose_file" -f "$update_file" "$@"
}

container_id=$(compose "$target_image" always ps -q nasdrop)
[ -n "$container_id" ] || { echo "NASDrop update: the Compose-managed nasdrop service is not running." >&2; exit 69; }

old_image_id=$(docker inspect --format '{{.Image}}' "$container_id")
config_source=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/config"}}{{.Source}}{{end}}{{end}}' "$container_id")
[ -n "$config_source" ] || { echo "NASDrop update: the /config bind mount was not found." >&2; exit 65; }

echo "NASDrop update: checking $target_image"
compose "$target_image" always pull nasdrop
new_image_id=$(docker image inspect --format '{{.Id}}' "$target_image")

if [ "$old_image_id" = "$new_image_id" ]; then
  echo "NASDrop update: already current."
  exit 0
fi

stamp=$(date '+%Y%m%d-%H%M%S')
rollback_image="nasdrop-local-rollback:$stamp"
docker image tag "$old_image_id" "$rollback_image"

echo "NASDrop update: stopping NASDrop for a consistent configuration backup."
compose "$target_image" always stop --timeout 60 nasdrop
mkdir -p "$backup_dir"
backup_file="$backup_dir/config-$stamp.tar.gz"
if ! tar -czf "$backup_file" -C "$config_source" .; then
  echo "NASDrop update: backup failed; restarting the existing container." >&2
  compose "$target_image" always start nasdrop || true
  exit 74
fi

wait_healthy() {
  waited=0
  while [ "$waited" -lt "$timeout" ]; do
    current_id=$(compose "$1" "$2" ps -q nasdrop)
    if [ -n "$current_id" ]; then
      state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$current_id" 2>/dev/null || true)
      [ "$state" = healthy ] && return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  return 1
}

echo "NASDrop update: installing the new image."
if compose "$target_image" always up -d --no-deps nasdrop && wait_healthy "$target_image" always; then
  echo "NASDrop update: complete; backup saved to $backup_file"
  echo "NASDrop update: rollback image retained as $rollback_image"
  exit 0
fi

echo "NASDrop update: health check failed; restoring $rollback_image" >&2
compose "$rollback_image" never up -d --no-deps nasdrop || true
if wait_healthy "$rollback_image" never; then
  echo "NASDrop update: previous image restored; configuration backup is $backup_file" >&2
else
  echo "NASDrop update: automatic rollback also failed; inspect docker compose logs nasdrop." >&2
fi
exit 70

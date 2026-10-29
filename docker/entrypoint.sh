#!/bin/sh
# Runs the panel (and the BeamMP servers it spawns) as PUID:PGID so files on the host
# get the right owner. Unraid's defaults are 99:100 (nobody:users).
set -e

PUID="${PUID:-99}"
PGID="${PGID:-100}"

if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA_DIR" "$BACKUP_DIR"
  chown -R "$PUID:$PGID" "$DATA_DIR" "$BACKUP_DIR"
  exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups env HOME="$DATA_DIR" "$@"
fi
exec "$@"

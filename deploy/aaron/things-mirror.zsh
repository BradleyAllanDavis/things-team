#!/bin/zsh
# Things DB snapshot mirror — copies the TCC-protected Things database to
# ~/.cache/things-mirror/main.sqlite so the spoke (stock python3) can read
# todos without a per-binary disk-access grant.
#
# Runs as /bin/zsh (a stable Apple platform binary) so a ONE-TIME manual
# Full Disk Access grant to /bin/zsh survives every update:
#   System Settings → Privacy & Security → Full Disk Access → + → /bin/zsh
#   (⌘⇧G in the file picker to type the path)
#
# The copy is `sqlite3 VACUUM INTO` — a transactionally consistent snapshot —
# written to a temp file and atomically renamed, so readers never see a torn db.

setopt null_glob
DEST_DIR="$HOME/.cache/things-mirror"
mkdir -p "$DEST_DIR"

srcs=("$HOME/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac"/ThingsData-*/"Things Database.thingsdatabase"/main.sqlite)
if (( ${#srcs} == 0 )); then
  echo "$(date +%FT%T) no Things database visible — Things not installed, or /bin/zsh lacks Full Disk Access"
  exit 1
fi
src="${srcs[1]}"

# Skip when unchanged — cheap stat vs a full copy. -wal carries most writes.
cur=$(/usr/bin/stat -f '%m %z' "$src" "$src-wal" 2>/dev/null)
if [[ -z "$cur" ]]; then
  echo "$(date +%FT%T) cannot stat source — grant Full Disk Access to /bin/zsh"
  exit 1
fi
marker="$DEST_DIR/src-state"
if [[ -f "$marker" && -f "$DEST_DIR/main.sqlite" && "$(<"$marker")" == "$cur" ]]; then
  exit 0
fi

tmp="$DEST_DIR/.main.sqlite.tmp"
rm -f "$tmp"
if /usr/bin/sqlite3 -readonly "$src" "VACUUM INTO '$tmp'"; then
  /bin/mv -f "$tmp" "$DEST_DIR/main.sqlite"
  printf '%s\n' "$cur" > "$marker"
  echo "$(date +%FT%T) mirrored $(/usr/bin/stat -f %z "$DEST_DIR/main.sqlite") bytes"
else
  rm -f "$tmp"
  echo "$(date +%FT%T) mirror copy failed — grant Full Disk Access to /bin/zsh"
  exit 1
fi

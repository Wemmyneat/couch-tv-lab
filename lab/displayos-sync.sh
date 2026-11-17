#!/usr/bin/env bash
# Copy DisplayOS's config from this Mac to the bridge, so the TV's wall rotates the same dashboards.
# The bridge reads it fresh whenever the file changes. Secrets are not in this file (DisplayOS keeps
# its tokens in the macOS Keychain).
#   lab/displayos-sync.sh            copy once
#   lab/displayos-sync.sh --watch    install a LaunchAgent that copies on every save
set -euo pipefail
SRC="$HOME/Library/Application Support/DisplayOS/displayos.yaml"
HOST="${DEPLOY_HOST:-wemserver-lan}"
DEST=/var/lib/couchtv/displayos.yaml
[ -f "$SRC" ] || { echo "no DisplayOS config at $SRC"; exit 1; }

if [ "${1:-}" = --watch ]; then
  PLIST="$HOME/Library/LaunchAgents/dev.couchtv-lab.displayos-sync.plist"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>dev.couchtv-lab.displayos-sync</string>
  <key>ProgramArguments</key><array><string>$(cd "$(dirname "$0")" && pwd)/displayos-sync.sh</string></array>
  <key>WatchPaths</key><array><string>$SRC</string></array>
  <key>StandardErrorPath</key><string>/tmp/displayos-sync.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/dev.couchtv-lab.displayos-sync" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "watching $SRC (undo: launchctl bootout gui/$(id -u)/dev.couchtv-lab.displayos-sync && rm $PLIST)"
fi

scp -q "$SRC" "$HOST:$DEST.tmp"
ssh "$HOST" "chown root:couchtv '$DEST.tmp' && chmod 640 '$DEST.tmp' && mv '$DEST.tmp' '$DEST'"
echo "synced DisplayOS config to $HOST:$DEST"

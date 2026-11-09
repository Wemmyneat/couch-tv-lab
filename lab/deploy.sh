#!/usr/bin/env bash
# Deploy this checkout to the bridge server.
#   lab/deploy.sh            copy code, keep the server's config.json/.env/data, restart the bridge
#   lab/deploy.sh --remote   also build the phone remote here (npm ci && npm run build) and ship remote/dist
#   lab/deploy.sh --web      copy only; the TV home page (tv-home/web) is served from disk, no restart needed
# Server and path: DEPLOY_HOST (default wemserver-lan), DEPLOY_DIR (default /opt/couch-tv-lab).
set -euo pipefail
HOST="${DEPLOY_HOST:-wemserver-lan}"; DIR="${DEPLOY_DIR:-/opt/couch-tv-lab}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# The phone remote is built on this computer and only its output is shipped, so the service user never
# runs npm or writes code on the server.
if [ "${1:-}" = --remote ]; then (cd "$ROOT/remote" && npm ci --no-audit --no-fund --loglevel=error && npm run build >/dev/null) && echo "remote built"; fi
rsync -a --delete \
  --exclude .git --exclude .venv --exclude dist --exclude build --exclude node_modules \
  --exclude config.json --exclude .env --exclude bridge/data --exclude tvs/ \
  --exclude 'lab/**/out-*' --exclude 'lab/**/backup-*' \
  "$ROOT/" "$HOST:$DIR/"
# Code stays root's: the service user can write only its data, its config (pairing marks it) and the
# remote's build output, never the code it runs.
ssh "$HOST" "chown -R root:root '$DIR' && chmod -R go-w '$DIR' && install -d -o couchtv -g couchtv '$DIR/bridge/data' && chown -R couchtv:couchtv '$DIR/bridge/data' && chown couchtv:couchtv '$DIR/config.json' && chown root:couchtv '$DIR/.env' && chmod 640 '$DIR/.env'"
case "${1:-}" in
  --web) echo "copied (no restart)";;
  --remote) ssh "$HOST" "systemctl restart couch-tv-bridge && sleep 3 && systemctl is-active couch-tv-bridge";;
  *) ssh "$HOST" "cd '$DIR' && .venv/bin/pip install -q --disable-pip-version-check -r bridge/requirements.txt && systemctl restart couch-tv-bridge && sleep 3 && systemctl is-active couch-tv-bridge";;
esac

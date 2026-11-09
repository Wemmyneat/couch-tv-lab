#!/usr/bin/env bash
# Deploy this checkout to the bridge server.
#   lab/deploy.sh            copy code, keep the server's config.json/.env/data, restart the bridge
#   lab/deploy.sh --remote   also rebuild the phone remote (npm ci && npm run build)
#   lab/deploy.sh --web      copy only; the TV home page (tv-home/web) is served from disk, no restart needed
# Server and path: DEPLOY_HOST (default wemserver-lan), DEPLOY_DIR (default /opt/couch-tv-lab).
set -euo pipefail
HOST="${DEPLOY_HOST:-wemserver-lan}"; DIR="${DEPLOY_DIR:-/opt/couch-tv-lab}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
rsync -a --delete \
  --exclude .git --exclude .venv --exclude dist --exclude build --exclude node_modules --exclude remote/dist \
  --exclude config.json --exclude .env --exclude bridge/data --exclude tvs/ \
  --exclude 'lab/**/out-*' --exclude 'lab/**/backup-*' \
  "$ROOT/" "$HOST:$DIR/"
ssh "$HOST" "chown -R couchtv:couchtv '$DIR'"
case "${1:-}" in
  --web) echo "copied (no restart)";;
  --remote)
    ssh "$HOST" "cd '$DIR/remote' && runuser -u couchtv -- env HOME=/var/lib/couchtv npm ci --no-audit --no-fund --loglevel=error && runuser -u couchtv -- env HOME=/var/lib/couchtv npm run build >/dev/null && echo 'remote built'"
    ssh "$HOST" "systemctl restart couch-tv-bridge && sleep 3 && systemctl is-active couch-tv-bridge";;
  *) ssh "$HOST" "cd '$DIR' && runuser -u couchtv -- .venv/bin/pip install -q --disable-pip-version-check -r bridge/requirements.txt && systemctl restart couch-tv-bridge && sleep 3 && systemctl is-active couch-tv-bridge";;
esac

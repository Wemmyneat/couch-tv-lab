#!/usr/bin/env bash
# Bring upstream couch-tv into couch-tv-lab on its own branch, then run every check (lab/UPSTREAM.md).
#   lab/sync-upstream.sh           fetch upstream, branch sync/upstream-<date> from main, merge, check
#   lab/sync-upstream.sh --check   only the checks (after resolving conflicts and committing)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python

check() {
  echo "== compile and shell syntax (as upstream CI)"
  $PY -m py_compile bridge/*.py scripts/*.py tv-home/tools/*.py sync/sync.py
  for f in scripts/*.sh tv-home/tools/*.sh sync/*.sh lab/*.sh; do
    if head -1 "$f" | grep -q bash; then bash -n "$f"; else sh -n "$f"; fi
  done
  echo "== Python tests (example config, not this computer's own config.json)"
  $PY -m pip install -q --disable-pip-version-check -r bridge/requirements.txt pytest
  COUCH_CONFIG="$PWD/config.example.json" $PY -m pytest tests -q --ignore=tests/fake-player -p no:warnings | tail -5 || true
  echo "== phone remote build"
  (cd remote && npm ci --no-audit --no-fund --loglevel=error && npm run build >/dev/null) && echo "remote ok"
  echo "== the fork's own files compile"
  $PY -m py_compile bridge/lab.py bridge/mcp_server.py
  node -e "new Function(require('fs').readFileSync('tv-home/web/app.js','utf8'))" && echo "app.js parses"
  echo
  echo "Next: build the TV app (scripts/build-apk.sh or the gradle line in lab/LAB.md), lab/deploy.sh --remote,"
  echo "the TV checklist in lab/UPSTREAM.md, then a PR into main."
}

if [ "${1:-}" = --check ]; then check; exit 0; fi

git diff --quiet && git diff --cached --quiet || { echo "commit or stash your changes first"; exit 1; }
git remote get-url upstream >/dev/null 2>&1 || git remote add upstream https://github.com/Seagey/couch-tv.git
git fetch -q upstream
git fetch -q origin
BR="sync/upstream-$(date +%F)"
git switch -q main && git merge -q --ff-only origin/main
NEW=$(git rev-list --count main..upstream/main)
[ "$NEW" -gt 0 ] || { echo "already up to date with upstream"; exit 0; }
echo "$NEW new upstream commits"
git switch -q -c "$BR"
if ! git merge --no-ff --no-edit upstream/main >/dev/null 2>&1; then
  echo "conflicts to resolve on $BR (lab/UPSTREAM.md, rule 2 first):"
  git diff --name-only --diff-filter=U | sed 's/^/  /'
  echo "then: git add <files> && git commit, and run lab/sync-upstream.sh --check"
  exit 1
fi
check

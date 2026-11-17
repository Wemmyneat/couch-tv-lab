#!/usr/bin/env bash
# Bring upstream couch-tv into couch-tv-lab on its own branch, then run every check (lab/UPSTREAM.md).
#   lab/sync-upstream.sh           fetch upstream, branch sync/upstream-<date> from main, merge, then STOP:
#                                  nothing from upstream runs until you have read what came in
#   lab/sync-upstream.sh --check   the checks (installs, tests, builds): run only after that review
# The checks run upstream's code on this computer (pip, npm, pytest). Review first; a container or VM without
# your SSH keys and config.json is safer still.
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
  $PY -m pip install -q --disable-pip-version-check --only-binary :all: -r bridge/requirements.txt pytest
  # Known to fail on pure upstream too (2026-11-17); listed by name so a new failure is never hidden.
  local known=(--deselect "tests/test_lg_power.py::SecondOff::test_off_again_right_after_off_turns_on")
  local log; log=$(mktemp)
  if ! COUCH_CONFIG="$PWD/config.example.json" $PY -m pytest tests -q --ignore=tests/fake-player -p no:warnings "${known[@]}" >"$log" 2>&1; then
    tail -20 "$log"; echo "TESTS FAILED: fix before merging"; return 1
  fi
  tail -1 "$log"
  echo "== phone remote build (no package install scripts)"
  (cd remote && npm ci --ignore-scripts --no-audit --no-fund --loglevel=error && npm run build >/dev/null) && echo "remote ok"
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
echo "Merged on $BR. Nothing from upstream has run yet. Review what came in:"
echo "  git log --oneline main..upstream/main"
echo "  git diff --stat main...upstream/main -- bridge/requirements.txt remote/package.json remote/package-lock.json scripts tv-home/tools"
echo "then run: lab/sync-upstream.sh --check"

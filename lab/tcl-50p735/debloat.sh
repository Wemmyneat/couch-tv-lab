#!/usr/bin/env bash
# Disable (or re-enable) the packages in debloat.txt on an Android TV over network ADB.
#
#   ./debloat.sh plan   <tv-ip>   show what would change, change nothing (default)
#   ./debloat.sh apply  <tv-ip>   back up states, then pm disable-user each package
#   ./debloat.sh undo   <tv-ip>   pm enable each package in debloat.txt
#
# Never uninstalls. Refuses to touch packages on the KEEP guard list even if they are added to debloat.txt.
set -euo pipefail
MODE="${1:-plan}"; TV="${2:?usage: debloat.sh plan|apply|undo <tv-ip>}:5555"
DIR="$(cd "$(dirname "$0")" && pwd)"
LIST="$DIR/debloat.txt"
GUARD='^(com\.google\.android\.apps\.tv\.launcherx|com\.google\.android\.tungsten\.setupwraith|com\.google\.android\.katniss|com\.google\.android\.tv\.assistant|com\.google\.android\.gms|com\.google\.android\.gsf|com\.google\.android\.webview|com\.google\.android\.apps\.mediashell|com\.tcl\.tv|com\.tcl\.tvinput|com\.tcl\.system\.server|com\.tcl\.settings|com\.tcl\.tcl_bt_rcu_service|com\.tcl\.autopair|com\.tcl\.micmanager|com\.android\..*)$'

sh_() { adb -s "$TV" shell "$@" | tr -d '\r'; }
adb connect "$TV" >/dev/null
[ "$(adb -s "$TV" get-state 2>/dev/null)" = device ] || { echo "TV not authorised/reachable at $TV"; exit 1; }

PKGS=$(sed -E 's/#.*//; s/[[:space:]]+//g; /^$/d' "$LIST")
INSTALLED=$(sh_ pm list packages | sed 's/package://')
DISABLED=$(sh_ pm list packages -d | sed 's/package://')

if [ "$MODE" = apply ]; then
  BK="$DIR/backup-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$BK"
  echo "$INSTALLED" > "$BK/installed.txt"; echo "$DISABLED" > "$BK/disabled-before.txt"
  sh_ cmd package resolve-activity --brief -c android.intent.category.HOME -a android.intent.action.MAIN > "$BK/home.txt"
  echo "Backup: $BK"
fi

for p in $PKGS; do
  if [[ "$p" =~ $GUARD ]]; then echo "GUARD  $p  (protected, skipped)"; continue; fi
  if ! grep -qx "$p" <<<"$INSTALLED"; then echo "ABSENT $p"; continue; fi
  isdis=$(grep -qx "$p" <<<"$DISABLED" && echo y || echo n)
  case "$MODE" in
    plan)  [ $isdis = y ] && echo "done   $p" || echo "would disable  $p" ;;
    apply) if [ $isdis = y ]; then echo "done   $p"; else printf 'disable %-45s ' "$p"; sh_ pm disable-user --user 0 "$p"; fi ;;
    undo)  printf 'enable  %-45s ' "$p"; sh_ pm enable "$p" ;;
    *) echo "unknown mode $MODE"; exit 1 ;;
  esac
done

if [ "$MODE" = apply ]; then
  echo; echo "Home is now: $(sh_ cmd package resolve-activity --brief -c android.intent.category.HOME -a android.intent.action.MAIN | tail -1)"
  echo "Next: reboot the TV (adb -s $TV reboot), then run the checks in CHECKLIST.md."
fi
